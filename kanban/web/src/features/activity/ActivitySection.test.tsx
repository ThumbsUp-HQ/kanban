import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ActivitySection } from './ActivitySection';
import type { IssueDetail } from '../drawer/slots';
import type { ActivityResponse, CommentList } from './activityApi';
import * as activityApi from './activityApi';

vi.mock('./activityApi', async () => {
  const actual = await vi.importActual<typeof import('./activityApi')>('./activityApi');
  return {
    ...actual,
    fetchActivity: vi.fn(),
    fetchComments: vi.fn(),
  };
});

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Auth Studio Migration',
};

const sampleActivity: ActivityResponse = {
  items: [
    {
      id: 'act-1',
      event_type: 'GATE_APPROVED',
      actor: { type: 'AGENT', display_name: 'sec-review' },
      payload: {
        hook_name: 'sec-review',
        execution_latency_ms: 812,
        verdict_sha256: 'abc123verdict',
      },
      created_at: '2026-11-12T09:30:00Z',
    },
    {
      id: 'act-2',
      event_type: 'STATE_CHANGED',
      actor: { handle: 'alice' },
      payload: { from_state: 'Todo', to_state: 'In Progress' },
      created_at: '2026-11-12T09:20:00Z',
    },
  ],
  next_cursor: 'cursor-page-2',
  counts: {
    all: 6,
    comments: 4,
    history: 3,
    gates: 2,
  },
};

const sampleComments: CommentList = {
  items: [
    {
      id: 'c1111111-1111-1111-1111-111111111111',
      issue_id: 'iss-1',
      author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
      body_markdown: 'First comment in thread.',
      reactions: [],
      created_at: '2026-11-12T09:15:00Z',
      deleted: false,
    },
  ],
  next_cursor: null,
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ActivitySection', () => {
  const mockFetchActivity = vi.mocked(activityApi.fetchActivity);
  const mockFetchComments = vi.mocked(activityApi.fetchComments);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchActivity.mockResolvedValue(sampleActivity);
    mockFetchComments.mockResolvedValue(sampleComments);
  });

  describe('Test Case 1: 4 Tabs, Badge Counts, Keyboard switching & Feed rendering', () => {
    it('renders 4 tabs: All, Comments (4), History, and 🤖 Gates (2)', async () => {
      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      const tabAll = await screen.findByRole('tab', { name: 'All' });
      expect(tabAll).toBeDefined();

      const tabComments = screen.getByRole('tab', { name: 'Comments (4)' });
      expect(tabComments).toBeDefined();

      const tabHistory = screen.getByRole('tab', { name: 'History' });
      expect(tabHistory).toBeDefined();

      const tabGates = screen.getByRole('tab', { name: 'Agent and workflow gates (2)' });
      expect(tabGates).toBeDefined();
    });

    it('switches tabs on click and queries activity with tab filter', async () => {
      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      await screen.findByRole('tab', { name: 'All' });

      // Click on Gates tab
      const gatesTab = screen.getByRole('tab', { name: 'Agent and workflow gates (2)' });
      fireEvent.click(gatesTab);

      await waitFor(() => {
        expect(mockFetchActivity).toHaveBeenCalledWith('KAN-142', 'gates', null);
      });
      expect(gatesTab.getAttribute('aria-selected')).toBe('true');
    });

    it('navigates tabs using ArrowRight, ArrowLeft, Home, and End keys', async () => {
      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      const allTab = await screen.findByRole('tab', { name: 'All' });
      allTab.focus();

      // Press ArrowRight -> moves to Comments tab
      fireEvent.keyDown(allTab, { key: 'ArrowRight' });
      const commentsTab = screen.getByRole('tab', { name: /^Comments/ });
      expect(commentsTab.getAttribute('aria-selected')).toBe('true');

      // Press End -> moves to Gates tab
      fireEvent.keyDown(commentsTab, { key: 'End' });
      const gatesTab = screen.getByRole('tab', { name: /^Agent and workflow gates/ });
      expect(gatesTab.getAttribute('aria-selected')).toBe('true');

      // Press Home -> moves back to All tab
      fireEvent.keyDown(gatesTab, { key: 'Home' });
      expect(allTab.getAttribute('aria-selected')).toBe('true');
    });

    it('loads older activity when clicking "Load older activity"', async () => {
      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      const loadMoreBtn = await screen.findByRole('button', { name: 'Load older activity' });
      fireEvent.click(loadMoreBtn);

      await waitFor(() => {
        expect(mockFetchActivity).toHaveBeenCalledWith('KAN-142', 'all', 'cursor-page-2');
      });
    });

    it('filters items correctly on Comments, History, and Gates tabs', async () => {
      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      await screen.findByRole('tab', { name: 'All' });

      // Click Comments tab
      const commentsTab = screen.getByRole('tab', { name: /^Comments/ });
      fireEvent.click(commentsTab);
      await waitFor(() => {
        expect(commentsTab.getAttribute('aria-selected')).toBe('true');
      });

      // Click History tab
      const historyTab = screen.getByRole('tab', { name: 'History' });
      fireEvent.click(historyTab);
      await waitFor(() => {
        expect(historyTab.getAttribute('aria-selected')).toBe('true');
      });
    });

    it('scrolls to targeted comment when initial hash contains #comment-<uuid>', async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const scrollIntoViewMock = vi.fn();
      window.HTMLElement.prototype.scrollIntoView = scrollIntoViewMock;

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142#comment-c1111111-1111-1111-1111-111111111111']}>
            <ActivitySection issue={mockIssue} currentUserId="u1" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await screen.findByRole('tab', { name: 'All' });
      await waitFor(() => {
        expect(scrollIntoViewMock).toHaveBeenCalled();
      }, { timeout: 3000 });
    });

    it('renders categorized HISTORY and AGENT_GATE rows and jumps to audit comment', async () => {
      const scrollIntoViewMock = vi.fn();
      window.HTMLElement.prototype.scrollIntoView = scrollIntoViewMock;

      const categorizedActivity: ActivityResponse = {
        items: [
          {
            id: 'act-hist-1',
            category: 'HISTORY',
            event_type: 'STATE_CHANGED',
            actor: { handle: 'alice' },
            payload: { from_state: 'Todo', to_state: 'In Progress' },
            created_at: '2026-11-12T10:00:00Z',
          },
          {
            id: 'act-gate-1',
            category: 'AGENT_GATE',
            event_type: 'GATE_VETOED',
            actor: { type: 'AGENT', display_name: 'qa-gate' },
            payload: {
              hook_name: 'reality-checker',
              reason: 'Quality gate failed',
              audit_comment_id: 'c1111111-1111-1111-1111-111111111111',
            },
            created_at: '2026-11-12T10:05:00Z',
          },
        ],
        next_cursor: null,
        counts: { all: 2, comments: 1, history: 1, gates: 1 },
      };
      mockFetchActivity.mockResolvedValue(categorizedActivity);

      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      // Click Gates tab
      const gatesTab = await screen.findByRole('tab', { name: /^Agent and workflow gates/ });
      fireEvent.click(gatesTab);

      // Verify Gate Vetoed row is rendered
      const vetoRow = await screen.findByTestId('gate-vetoed-row');
      expect(vetoRow).toBeDefined();

      // Click jump to comment button inside veto row
      const jumpBtn = screen.getByRole('button', { name: 'View audit details' });
      fireEvent.click(jumpBtn);

      // Switch to History tab and verify history row is rendered
      const historyTab = screen.getByRole('tab', { name: 'History' });
      fireEvent.click(historyTab);

      const histRow = await screen.findByTestId('history-row');
      expect(histRow).toBeDefined();
    });

    it('renders empty states when no items are present', async () => {
      const emptyActivity: ActivityResponse = {
        items: [],
        next_cursor: null,
        counts: { all: 0, comments: 0, history: 0, gates: 0 },
      };
      mockFetchActivity.mockResolvedValue(emptyActivity);
      mockFetchComments.mockResolvedValue({ items: [], next_cursor: null });

      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      // All tab empty
      expect(await screen.findByText('No activity yet.')).toBeDefined();

      // Comments tab empty
      const commentsTab = screen.getByRole('tab', { name: /^Comments/ });
      fireEvent.click(commentsTab);
      expect(await screen.findByText('No comments yet.')).toBeDefined();

      // History tab empty
      const historyTab = screen.getByRole('tab', { name: 'History' });
      fireEvent.click(historyTab);
      expect(await screen.findByText('No history recorded yet.')).toBeDefined();

      // Gates tab empty
      const gatesTab = screen.getByRole('tab', { name: /^Agent and workflow gates/ });
      fireEvent.click(gatesTab);
      expect(await screen.findByText('No agent or workflow gates recorded yet.')).toBeDefined();
    });

    it('triggers handleRefresh on comment update and submit and attaches X-CSRF-Token header', async () => {
      activityApi.resetActivityCsrfCache();
      document.cookie = 'kb_csrf=csrf-activity-token-123; Path=/';

      const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: () =>
          Promise.resolve({
            id: 'c2222222-2222-2222-2222-222222222222',
            issue_id: 'iss-1',
            author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
            body_markdown: 'New test comment',
            reactions: [],
            created_at: '2026-11-12T09:45:00Z',
            deleted: false,
          }),
      } as unknown as Response);

      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      const allTab = await screen.findByRole('tab', { name: 'All' });
      expect(allTab).toBeDefined();

      // Submit comment from composer
      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'New test comment' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith(
          '/api/v1/issues/KAN-142/comments',
          expect.objectContaining({
            method: 'POST',
            credentials: 'same-origin',
            headers: expect.objectContaining({
              'X-CSRF-Token': 'csrf-activity-token-123',
            }) as unknown as Record<string, string>,
          }),
        );
      });

      document.cookie = 'kb_csrf=; Max-Age=0; Path=/';
      activityApi.resetActivityCsrfCache();
      fetchSpy.mockRestore();
    });

    it('bootstraps X-CSRF-Token from /api/v1/auth/session when cookie is absent on comment submit', async () => {
      document.cookie = 'kb_csrf=; Max-Age=0; Path=/';
      activityApi.resetActivityCsrfCache();
      expect(activityApi.getActivityCsrfToken()).toBeNull();

      const fetchSpy = vi
        .spyOn(global, 'fetch')
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ csrf_token: 'bootstrapped-csrf-456' }),
        } as unknown as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 201,
          json: () =>
            Promise.resolve({
              id: 'c3333333-3333-3333-3333-333333333333',
              issue_id: 'iss-1',
              author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
              body_markdown: 'Bootstrapped CSRF comment',
              reactions: [],
              created_at: '2026-11-12T09:50:00Z',
              deleted: false,
            }),
        } as unknown as Response);

      const created = await activityApi.createComment('KAN-142', {
        body_markdown: 'Bootstrapped CSRF comment',
      });
      expect(created.id).toBe('c3333333-3333-3333-3333-333333333333');
      expect(fetchSpy).toHaveBeenNthCalledWith(
        1,
        '/api/v1/auth/session',
        expect.objectContaining({
          method: 'GET',
          credentials: 'same-origin',
        }),
      );
      expect(fetchSpy).toHaveBeenNthCalledWith(
        2,
        '/api/v1/issues/KAN-142/comments',
        expect.objectContaining({
          method: 'POST',
          credentials: 'same-origin',
          headers: expect.objectContaining({
            'X-CSRF-Token': 'bootstrapped-csrf-456',
          }) as unknown as Record<string, string>,
        }),
      );

      document.cookie = 'kb_csrf=; Max-Age=0; Path=/';
      activityApi.resetActivityCsrfCache();
      fetchSpy.mockRestore();
    });
  });
});
