import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { YourWorkView } from './YourWorkView';
import { apiFetch } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const mockApiFetch = vi.mocked(apiFetch);

const mockUser = {
  id: 'user-123',
  handle: 'alice',
  display_name: 'Alice Developer',
  email: 'alice@example.com',
};

const mockProjects = [
  { id: 'proj-1', key: 'KAN', name: 'Kanban Project' },
  { id: 'proj-2', key: 'OPS', name: 'Operations' },
];

const mockIssuesKan: unknown[] = [
  {
    id: 'iss-1',
    key: 'KAN-101',
    summary: 'Fix session timeout error',
    project_key: 'KAN',
    created_by_id: 'user-123',
    created_by_handle: 'alice',
    state: { id: 's-1', name: 'In Progress', slug: 'in_progress', group: 'in_progress', color: '#2563eb' },
    priority: { id: 'p-1', name: 'High', slug: 'high', label: 'High' },
    assignees: [
      { id: 'user-123', principal: { id: 'user-123', handle: 'alice', display_name: 'Alice' } },
    ],
    subscribed: true,
  },
  {
    id: 'iss-2',
    key: 'KAN-102',
    summary: 'Implement OAuth passkeys',
    project_key: 'KAN',
    created_by_id: 'user-999',
    created_by_handle: 'bob',
    state: { id: 's-2', name: 'Todo', slug: 'todo', group: 'todo', color: '#64748b' },
    priority: { id: 'p-2', name: 'Urgent', slug: 'urgent', label: 'Urgent' },
    assignees: [
      { id: 'user-999', principal: { id: 'user-999', handle: 'bob', display_name: 'Bob' } },
    ],
    subscribed: false,
  },
];

const mockIssuesOps: unknown[] = [
  {
    id: 'iss-3',
    key: 'OPS-201',
    summary: 'Deploy backup container',
    project_key: 'OPS',
    created_by_id: 'user-999',
    created_by_handle: 'bob',
    state: { id: 's-3', name: 'Done', slug: 'done', group: 'completed', color: '#16a34a' },
    priority: { id: 'p-3', name: 'Low', slug: 'low', label: 'Low' },
    assignees: [
      { id: 'a-ext', kind: 'free_text', free_text: 'alice' },
    ],
    subscribed: false,
  },
];

const mockNotifications = {
  items: [
    {
      id: 'notif-1',
      issue: { id: 'iss-2', key: 'KAN-102', summary: 'Implement OAuth passkeys' },
      event_type: 'COMMENT_CREATED',
    },
    {
      id: 'notif-link-1',
      link: '/projects/KAN/issues?peek=KAN-101',
      event_type: 'ASSIGNED',
    },
    {
      id: 'notif-link-2',
      link: '/projects/KAN/docs',
      event_type: 'SYSTEM',
    },
    {
      id: 'notif-no-link',
      event_type: 'SYSTEM',
    },
  ],
};

function renderComponent() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/your-work']}>
        <YourWorkView />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('YourWorkView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      const p = path as string;
      if (p === '/api/v1/auth/me') return mockUser;
      if (p === '/api/v1/projects') return mockProjects;
      if (p.includes('/notifications')) return mockNotifications;
      if (p.includes('/projects/KAN/issues')) return mockIssuesKan;
      if (p.includes('/projects/OPS/issues')) return mockIssuesOps;
      return [];
    });
  });

  it('renders your work title, tabs with counts, and assigned issues by default', async () => {
    renderComponent();

    expect(screen.getByTestId('your-work-view')).toBeDefined();
    expect(screen.getByText('Your work')).toBeDefined();

    // Verify tabs
    expect(await screen.findByTestId('tab-assigned-to-me')).toBeDefined();
    expect(screen.getByTestId('tab-created-by-me')).toBeDefined();
    expect(screen.getByTestId('tab-subscribed')).toBeDefined();

    // Verify assigned items count and items
    await waitFor(() => {
      expect(screen.getByTestId('badge-assigned-count').textContent).toBe('2'); // KAN-101 (id match) + OPS-201 (free_text handle match)
    });

    expect(screen.getByText('KAN-101')).toBeDefined();
    expect(screen.getByText('Fix session timeout error')).toBeDefined();
    expect(screen.getByText('OPS-201')).toBeDefined();
    expect(screen.getByText('Deploy backup container')).toBeDefined();
  });

  it('switches to Created by Me tab and shows created items', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('badge-created-count').textContent).toBe('1');
    });

    const createdTab = screen.getByTestId('tab-created-by-me');
    fireEvent.click(createdTab);

    expect(createdTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('KAN-101')).toBeDefined();
    expect(screen.queryByText('OPS-201')).toBeNull();
  });

  it('switches to Subscribed tab and shows explicitly subscribed items and notifications items', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('badge-subscribed-count').textContent).toBe('2'); // KAN-101 (subscribed=true) + KAN-102 (in notifs)
    });

    const subTab = screen.getByTestId('tab-subscribed');
    fireEvent.click(subTab);

    expect(subTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('KAN-101')).toBeDefined();
    expect(screen.getByText('KAN-102')).toBeDefined();
  });

  it('filters active tab items using search input', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('KAN-101')).toBeDefined();
    });

    const searchInput = screen.getByLabelText('Filter your work items');
    fireEvent.change(searchInput, { target: { value: 'backup' } });

    expect(screen.queryByText('KAN-101')).toBeNull();
    expect(screen.getByText('OPS-201')).toBeDefined();

    // No match
    fireEvent.change(searchInput, { target: { value: 'nonexistent-xyz' } });
    expect(screen.getByTestId('your-work-empty')).toBeDefined();
    expect(screen.getByText(/No work items matching "nonexistent-xyz"/)).toBeDefined();
  });

  it('dispatches kb:open-issue-peek and updates url when clicking item or Inspect button', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('KAN-101')).toBeDefined();
    });

    const peekListener = vi.fn();
    window.addEventListener('kb:open-issue-peek', peekListener);

    const inspectBtn = screen.getByLabelText('Inspect KAN-101');
    fireEvent.click(inspectBtn);

    expect(peekListener).toHaveBeenCalled();
    const firstCall = peekListener.mock.calls[0];
    expect(firstCall).toBeDefined();
    const eventDetail = (firstCall?.[0] as CustomEvent<{ issueKey: string }> | undefined)?.detail;
    expect(eventDetail?.issueKey).toBe('KAN-101');

    // Also clicking card directly
    fireEvent.click(screen.getByTestId('your-work-item-KAN-101'));
    expect(peekListener).toHaveBeenCalledTimes(2);

    window.removeEventListener('kb:open-issue-peek', peekListener);
  });

  it('handles empty state when no items exist in accessible projects', async () => {
    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      const p = path as string;
      if (p === '/api/v1/auth/me') return mockUser;
      if (p === '/api/v1/projects') return [];
      if (p.includes('/notifications')) return { items: [] };
      return [];
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('your-work-empty')).toBeDefined();
    });
    expect(screen.getByText('No work items currently assigned to you.')).toBeDefined();

    // Switch to Created tab
    fireEvent.click(screen.getByTestId('tab-created-by-me'));
    expect(screen.getByText('You have not created any work items yet.')).toBeDefined();

    // Switch to Subscribed tab
    fireEvent.click(screen.getByTestId('tab-subscribed'));
    expect(screen.getByText('You are not subscribed to any work items yet.')).toBeDefined();
  });

  it('handles network / offline rejection gracefully', async () => {
    mockApiFetch.mockRejectedValue(new Error('Network offline'));
    renderComponent();

    await waitFor(() => {
      expect(screen.getByTestId('your-work-empty')).toBeDefined();
    });
    expect(screen.getByText('No work items currently assigned to you.')).toBeDefined();
  });
});
