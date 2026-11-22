import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  NotificationsBell,
  formatEventBadge,
  formatTimeAgo,
  isNotificationUnread,
} from './NotificationsBell';
import { apiFetch } from '../../api/client';
import { RealtimeClient } from '../../api/realtime';
import type { RealtimeState } from '../../api/RealtimeStatus';
import { RealtimeContext } from '../../realtime/context';

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

  describe('Realtime subscription, transport-gated fallback polling, recovery resync, and announcer (KAN-310)', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    function renderWithRealtime(client: RealtimeClient, state: RealtimeState, queryClient?: QueryClient) {
      const qc =
        queryClient ??
        new QueryClient({
          defaultOptions: { queries: { retry: false, gcTime: 0 } },
        });
      return render(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
    }

    it('subscribes to notifications:self, suppresses 30s polling while open/sse-fallback, and polls only when reconnecting/closed', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const client = new RealtimeClient();
      const subSpy = vi.spyOn(client, 'subscribe');
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });

      const { rerender, unmount } = renderWithRealtime(client, 'open', qc);
      const bell = await screen.findByTestId('notifications-bell');
      expect(subSpy).toHaveBeenCalledWith('notifications:self', expect.any(Function));
      expect(bell.getAttribute('data-realtime-state')).toBe('open');
      expect(bell.getAttribute('data-polling-active')).toBe('false');

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(1);
      });

      // Advance 65s while open -> 0 periodic polls
      await act(async () => {
        await vi.advanceTimersByTimeAsync(65000);
      });
      expect(mockApiFetch).toHaveBeenCalledTimes(1);

      // Switch to sse-fallback -> still 0 periodic polls over 65s
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'sse-fallback' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      expect(bell.getAttribute('data-realtime-state')).toBe('sse-fallback');
      expect(bell.getAttribute('data-polling-active')).toBe('false');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(65000);
      });
      expect(mockApiFetch).toHaveBeenCalledTimes(1);

      // Transition to reconnecting -> enables 30s fallback polling
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'reconnecting' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      expect(bell.getAttribute('data-realtime-state')).toBe('reconnecting');
      expect(bell.getAttribute('data-polling-active')).toBe('true');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });
      expect(mockApiFetch).toHaveBeenCalledTimes(2);

      unmount();
    });

    it('fires single-shot recovery resync on reconnecting|closed -> open|sse-fallback but not on connecting -> open', async () => {
      const client = new RealtimeClient();
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });

      const { rerender } = renderWithRealtime(client, 'connecting', qc);
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(1);
      });

      // connecting -> open must NOT trigger a second fetch
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'open' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      expect(mockApiFetch).toHaveBeenCalledTimes(1);

      // open -> reconnecting -> open MUST trigger a single-shot recovery resync
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'reconnecting' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'open' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(2);
      });

      // open -> closed -> sse-fallback MUST trigger a single-shot recovery resync
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'closed' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      rerender(
        <QueryClientProvider client={qc}>
          <RealtimeContext.Provider value={{ client, state: 'sse-fallback' }}>
            <MemoryRouter>
              <NotificationsBell />
            </MemoryRouter>
          </RealtimeContext.Provider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledTimes(3);
      });
    });

    it('updates unread badge across tabs on notification.created, notification.read, and notification.read_all and coalesces polite announcements', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const client = new RealtimeClient();
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });

      renderWithRealtime(client, 'open', qc);
      const badge = await screen.findByTestId('notifications-badge');
      expect(badge.textContent).toBe('2');

      // 1. Optimistic multi-tab notification.read decrements badge from 2 -> 1 without extra GET fetch
      const callsBeforeRead = mockApiFetch.mock.calls.length;
      await act(async () => {
        client.simulateEvent({
          id: 'evt-read-1',
          channel: 'notifications:self',
          type: 'notification.read',
          payload: { notification_id: 'notif-1', recipient_principal_id: 'u1' },
        });
        await vi.advanceTimersByTimeAsync(10);
      });
      expect(screen.getByTestId('notifications-badge').textContent).toBe('1');
      expect(mockApiFetch.mock.calls.length).toBe(callsBeforeRead);
      expect(screen.getByTestId('notifications-live-announcer').textContent).toBe('');

      // 2. Optimistic multi-tab notification.read_all clears badge from 1 -> 0 without extra GET fetch
      await act(async () => {
        client.simulateEvent({
          id: 'evt-read-all',
          channel: 'notifications:self',
          type: 'notification.read_all',
          payload: { marked_count: 1, recipient_principal_id: 'u1' },
        });
        await vi.advanceTimersByTimeAsync(10);
      });
      expect(screen.queryByTestId('notifications-badge')).toBeNull();
      expect(mockApiFetch.mock.calls.length).toBe(callsBeforeRead);

      // 3. Simulate single notification.created event -> announces '1 new notification' after 1000ms
      mockApiFetch.mockResolvedValue({
        items: [
          ...mockNotifications.items,
          {
            id: 'notif-4',
            issue: { id: 'iss-4', key: 'KAN-104', summary: 'New live arrival' },
            event_type: 'COMMENT_MENTION',
            actor: { handle: 'dana', display_name: 'Dana' },
            created_at: new Date().toISOString(),
            read_at: null,
          },
        ],
      });

      await act(async () => {
        client.simulateEvent({
          id: 'evt-created-single',
          channel: 'notifications:self',
          type: 'notification.created',
          payload: { notification_id: 'notif-4', recipient_principal_id: 'u1' },
        });
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByTestId('notifications-live-announcer').textContent).toBe(
        '1 new notification',
      );

      // 4. Simulate 2 rapid notification.created events while tray is closed -> coalesces announcement over 1000ms
      await act(async () => {
        client.simulateEvent({
          id: 'evt-created-1',
          channel: 'notifications:self',
          type: 'notification.created',
          payload: { notification_id: 'notif-4', recipient_principal_id: 'u1' },
        });
        client.simulateEvent({
          id: 'evt-created-2',
          channel: 'notifications:self',
          type: 'notification.created',
          payload: { notification_id: 'notif-5', recipient_principal_id: 'u1' },
        });
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByTestId('notifications-live-announcer').textContent).toBe(
        '2 new notifications',
      );
      expect((await screen.findByTestId('notifications-badge')).textContent).toBe('3');

      // 5. Simulate notification.read for an uncached ID -> falls back to invalidation
      await act(async () => {
        client.simulateEvent({
          id: 'evt-read-uncached',
          channel: 'notifications:self',
          type: 'notification.read',
          payload: { notification_id: 'notif-unknown', recipient_principal_id: 'u1' },
        });
        await vi.advanceTimersByTimeAsync(10);
      });

      // Opening the tray clears the live announcement
      fireEvent.click(screen.getByTestId('notifications-bell'));
      expect(screen.getByTestId('notifications-live-announcer').textContent).toBe('');
    });

    it('aligns unreadCount predicate for items with read: true and read_at: null', async () => {
      expect(isNotificationUnread({ id: '1', created_at: '2026-01-01T00:00:00Z', read_at: null, read: true })).toBe(false);
      expect(isNotificationUnread({ id: '2', created_at: '2026-01-01T00:00:00Z', read_at: null, read: false })).toBe(true);
      expect(isNotificationUnread({ id: '3', created_at: '2026-01-01T00:00:00Z', read_at: null })).toBe(true);
      expect(isNotificationUnread({ id: '4', created_at: '2026-01-01T00:00:00Z', read_at: '2026-01-02T00:00:00Z', read: false })).toBe(false);

      mockApiFetch.mockResolvedValue({
        items: [
          {
            id: 'notif-boolean-read',
            title: 'Fallback title item',
            created_at: new Date().toISOString(),
            read_at: null,
            read: true,
          },
          {
            id: 'notif-body-only',
            body: 'Fallback body item',
            type: 'ASSIGN',
            created_at: new Date().toISOString(),
            read_at: null,
          },
          {
            id: 'notif-default-text',
            issue: { key: 'KAN-999' },
            created_at: new Date().toISOString(),
            read_at: null,
          },
          {
            id: 'notif-bare',
            created_at: new Date().toISOString(),
            read_at: null,
          },
        ],
      });
      renderComponent();
      const bell = await screen.findByTestId('notifications-bell');
      fireEvent.click(bell);
      expect(await screen.findByText('Fallback title item')).toBeDefined();
      expect(screen.getByText('Fallback body item')).toBeDefined();
      expect(screen.getByText('Notification')).toBeDefined();
      expect(screen.getByTestId('notifications-badge').textContent).toBe('3');
    });

    it('handles apiFetch error fallback, cancels pending announcer timer on tray open or unmount, and covers fallback actor/item branches', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      mockApiFetch.mockRejectedValueOnce(new Error('network error'));
      const client = new RealtimeClient();
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });

      const { unmount } = renderWithRealtime(client, 'open', qc);
      const bell = await screen.findByTestId('notifications-bell');

      // Queue announcement timer, then open tray before 1000ms elapses -> timer cleared
      act(() => {
        client.simulateEvent({
          id: 'evt-cancel-open',
          channel: 'notifications:self',
          type: 'notification.created',
          payload: { notification_id: 'n-open' },
        });
      });
      mockApiFetch.mockResolvedValueOnce({});
      fireEvent.click(bell);
      // Clicking inside tray and pressing non-Escape key keeps tray open
      const tray = await screen.findByTestId('notifications-tray');
      fireEvent.mouseDown(tray);
      fireEvent.keyDown(window, { key: 'Enter' });
      expect(screen.getByTestId('notifications-tray')).toBeDefined();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      expect(screen.getByTestId('notifications-live-announcer').textContent).toBe('');

      // Close tray, queue another announcement timer, and unmount before 1000ms -> cleanup clears timer
      fireEvent.click(bell);
      act(() => {
        client.simulateEvent({
          id: 'evt-cancel-unmount',
          channel: 'notifications:self',
          type: 'notification.created',
          payload: { notification_id: 'n-unmount' },
        });
      });
      unmount();
    });
  });
});
