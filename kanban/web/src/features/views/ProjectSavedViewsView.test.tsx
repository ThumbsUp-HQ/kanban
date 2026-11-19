import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProjectSavedViewsView, ProjectSavedViewsViewInner } from './ProjectSavedViewsView';
import * as clientModule from '../../api/client';

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
}));

describe('ProjectSavedViewsView (KANBA-221)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  it('renders fallback links row when rendered without QueryClient', () => {
    render(
      <MemoryRouter initialEntries={['/projects/KAN/views']}>
        <ProjectSavedViewsView />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('project-views-view')).toBeDefined();
    expect(screen.getByRole('link', { name: 'List View' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Board View' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Table View' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Calendar View' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Timeline View' })).toBeDefined();
  });

  it('displays empty state when project has no custom saved views', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock.mockResolvedValueOnce({ views: [] });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/views']}>
          <Routes>
            <Route path="/projects/:projectKey/views" element={<ProjectSavedViewsView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('no-saved-views')).toBeDefined();
    expect(screen.getByText(/No custom saved views found for KAN/i)).toBeDefined();
  });

  it('renders list of saved views with metadata and badges', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock.mockResolvedValueOnce([
      {
        id: 'view-1',
        name: 'Sprint Backlog Board',
        description_markdown: 'Current active sprint items',
        layout: 'board',
        group_by: 'state',
        sub_group_by: 'priority',
        is_shared: true,
        filters: { search_query: 'auth' },
      },
      {
        id: 'view-2',
        name: 'My Private Table',
        description_markdown: null,
        layout: 'table',
        group_by: null,
        sub_group_by: null,
        is_shared: false,
        filters: null,
      },
    ]);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProjectSavedViewsViewInner projectKey="KAN" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Sprint Backlog Board')).toBeDefined();
    expect(screen.getByText('Current active sprint items')).toBeDefined();
    expect(screen.getByText('Shared')).toBeDefined();
    expect(screen.getByText('Private')).toBeDefined();
    expect(screen.getByText('Group: state')).toBeDefined();
    expect(screen.getByText('Sub-group: priority')).toBeDefined();
    expect(screen.getByText(/Search: "auth"/)).toBeDefined();

    const openLink = screen.getByTestId('open-view-view-1');
    expect(openLink.getAttribute('href')).toBe('/projects/KAN/issues?layout=board&view=view-1');
  });

  it('deletes a saved view when clicking delete', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock
      .mockResolvedValueOnce([
        {
          id: 'view-del',
          name: 'Deletable View',
          layout: 'list',
          is_shared: false,
        },
      ])
      .mockResolvedValueOnce({}) // for DELETE
      .mockResolvedValueOnce([]); // for subsequent refetch query

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProjectSavedViewsViewInner projectKey="KAN" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const deleteBtn = await screen.findByTestId('delete-view-view-del');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('DELETE', '/api/v1/views/view-del');
    });
  });

  it('renders error message when fetching saved views fails', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock.mockRejectedValueOnce(new Error('Network error loading views'));

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProjectSavedViewsViewInner projectKey="KAN" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('error-views')).toBeDefined();
    expect(screen.getByTestId('error-views').textContent).toContain('Network error loading views');
  });

  it('renders default error message when rejection is not an Error instance', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock.mockRejectedValueOnce('raw string rejection');

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProjectSavedViewsViewInner projectKey="KAN" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId('error-views')).toBeDefined();
    expect(screen.getByTestId('error-views').textContent).toContain('Failed to load saved views');
  });
});
