import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  NotificationsBell,
  formatEventBadge,
  formatTimeAgo,
} from './NotificationsBell';
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

const mockNotifications = {
  items: [
    {
      id: 'notif-1',
      issue: { id: 'iss-1', key: 'KAN-101', summary: 'Fix login error' },
      event_type: 'COMMENT_MENTION',
      actor: { handle: 'alice', display_name: 'Alice' },
      created_at: new Date(Date.now() - 5 * 60000).toISOString(), // 5m ago
      read_at: null,
    },
    {
      id: 'notif-2',
      issue: { id: 'iss-2', key: 'KAN-102', summary: 'Add passkeys support' },
      event_type: 'ASSIGNEE_ADDED',
      actor: { handle: 'bob', display_name: 'Bob' },
      created_at: new Date(Date.now() - 2 * 3600000).toISOString(), // 2h ago
      read_at: null,
    },
    {
      id: 'notif-3',
      issue: { id: 'iss-3', key: 'OPS-201', summary: 'Verify agent gate' },
      event_type: 'AGENT_GATE_FAILED',
      actor: { label: 'Reality Checker' },
      created_at: new Date(Date.now() - 86400000).toISOString(), // 1d ago
      read_at: '2026-01-01T00:00:00Z',
    },
  ],
};

function renderComponent() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotificationsBell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NotificationsBell & Feed Tray', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockResolvedValue(mockNotifications);
  });

  it('renders bell button with unread count badge (2 unread)', async () => {
    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    expect(bellBtn).toBeDefined();

    const badge = await screen.findByTestId('notifications-badge');
    expect(badge.textContent).toBe('2');
  });

  it('toggles notifications tray open and displays notification feed items', async () => {
    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    fireEvent.click(bellBtn);

    expect(await screen.findByTestId('notifications-tray')).toBeDefined();
    expect(screen.getByText('Notifications')).toBeDefined();
    expect(screen.getByText('Mark all read')).toBeDefined();

    // Verify items
    expect(screen.getByText('Fix login error')).toBeDefined();
    expect(screen.getByText('Add passkeys support')).toBeDefined();
    expect(screen.getByText('Verify agent gate')).toBeDefined();

    // Verify event badges
    expect(screen.getByText('@mention')).toBeDefined();
    expect(screen.getByText('assigned')).toBeDefined();
    expect(screen.getByText('🤖 gate')).toBeDefined();
  });

  it('handles clicking deep link to work item and dispatches kb:open-issue-peek', async () => {
    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    fireEvent.click(bellBtn);

    const peekListener = vi.fn();
    window.addEventListener('kb:open-issue-peek', peekListener);

    const link = await screen.findByTestId('notif-deep-link-KAN-101');
    fireEvent.click(link);

    expect(peekListener).toHaveBeenCalled();
    const firstCall = peekListener.mock.calls[0];
    expect(firstCall).toBeDefined();
    const evt = firstCall?.[0] as CustomEvent<{ issueKey: string }> | undefined;
    expect(evt?.detail.issueKey).toBe('KAN-101');

    // Tray closes after navigation
    expect(screen.queryByTestId('notifications-tray')).toBeNull();
    window.removeEventListener('kb:open-issue-peek', peekListener);
  });

  it('marks individual notification as read on checkmark click', async () => {
    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path.includes('/read')) return {};
      return mockNotifications;
    });

    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    fireEvent.click(bellBtn);

    const markReadBtn = await screen.findByTestId('mark-read-notif-1');
    fireEvent.click(markReadBtn);

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith('POST', '/api/v1/notifications/notif-1/read');
    });
  });

  it('marks all notifications as read on Mark all read click', async () => {
    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/notifications/read-all') return { marked: 2 };
      return mockNotifications;
    });

    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    fireEvent.click(bellBtn);

    const markAllBtn = await screen.findByTestId('mark-all-read-btn');
    fireEvent.click(markAllBtn);

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith('POST', '/api/v1/notifications/read-all');
    });
  });

  it('closes tray when Escape key is pressed or clicking outside', async () => {
    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    fireEvent.click(bellBtn);

    expect(await screen.findByTestId('notifications-tray')).toBeDefined();

    // Escape closes
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('notifications-tray')).toBeNull();

    // Reopen and click outside
    fireEvent.click(bellBtn);
    expect(await screen.findByTestId('notifications-tray')).toBeDefined();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('notifications-tray')).toBeNull();
  });

  it('renders empty state when there are 0 notifications', async () => {
    mockApiFetch.mockResolvedValue({ items: [] });
    renderComponent();

    const bellBtn = await screen.findByTestId('notifications-bell');
    fireEvent.click(bellBtn);

    expect(await screen.findByTestId('notifications-empty')).toBeDefined();
    expect(screen.getByText('No notifications yet')).toBeDefined();
    expect(screen.queryByTestId('notifications-badge')).toBeNull();
  });

  it('formatEventBadge and formatTimeAgo cover all helper branches', () => {
    expect(formatEventBadge('ISSUE_STATE_CHANGED').label).toBe('transition');
    expect(formatEventBadge('UNKNOWN_CUSTOM_EVENT').label).toBe('update');

    expect(formatTimeAgo(new Date(Date.now() - 10000).toISOString())).toBe('just now');
    expect(formatTimeAgo(new Date(Date.now() - 300000).toISOString())).toBe('5m ago');
    expect(formatTimeAgo(new Date(Date.now() - 7200000).toISOString())).toBe('2h ago');
    expect(formatTimeAgo(new Date(Date.now() - 172800000).toISOString())).toBe('2d ago');
    expect(formatTimeAgo('invalid-date')).toBe('');
  });

  it('covers >99 unread badge, nodash key deep link, and toggle close without refetch', async () => {
    const manyUnread = Array.from({ length: 105 }, (_, i) => ({
      id: `notif-${String(i)}`,
      issue: { id: `iss-${String(i)}`, key: 'NODASHKEY', summary: `Item ${String(i)}` },
      event_type: 'COMMENT_MENTION',
      actor: i === 0 ? { handle: 'charlie' } : {},
      created_at: new Date().toISOString(),
      read_at: null,
    }));
    mockApiFetch.mockResolvedValueOnce({ items: manyUnread });
    renderComponent();

    const badge = await screen.findByTestId('notifications-badge');
    expect(badge.textContent).toBe('99+');

    const bellBtn = screen.getByTestId('notifications-bell');
    // Open
    fireEvent.click(bellBtn);
    expect(await screen.findByTestId('notifications-tray')).toBeDefined();

    // Click item with nodash key
    const links = screen.getAllByText('NODASHKEY');
    const firstLink = links[0];
    if (firstLink) fireEvent.click(firstLink);
    expect(screen.queryByTestId('notifications-tray')).toBeNull();

    // Reopen and click bell again to close
    fireEvent.click(bellBtn);
    expect(await screen.findByTestId('notifications-tray')).toBeDefined();
    fireEvent.click(bellBtn);
    expect(screen.queryByTestId('notifications-tray')).toBeNull();
  });
});
