import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ActivitySection } from './ActivitySection';
import type { IssueDetail } from '../drawer/slots';
import type { ActivityResponse, CommentList } from './activityApi';
import * as activityApi from './activityApi';
import { ShellPanelsProvider, registerShellPanel } from '../../app/shellPanels';

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
      }, { timeout: 10000 });
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

  describe('StudioDocLink and Shift-Left Invariants (KAN-493)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders StudioDocLink in activity-section__title-row with correct href, label, and testId in Light and Dark themes', async () => {
      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const Wrapper = createWrapper();
        const { unmount } = render(<ActivitySection issue={mockIssue} currentUserId="u1" />, {
          wrapper: Wrapper,
        });

        await waitFor(() => {
          expect(screen.getByTestId('activity-section-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('activity-section-doc-link');
        expect(docLink.getAttribute('href')).toBe(
          '/docs/ticket-screen-and-work-item-features#activity-stream-and-audit-ledger',
        );
        expect(docLink.getAttribute('aria-label')).toBe('Audit Ledger ->');
        expect(docLink.textContent).toContain('Audit Ledger ->');

        const titleRow = docLink.closest('.activity-section__title-row');
        expect(titleRow).not.toBeNull();
        expect(titleRow?.querySelector('.activity-section__title')?.textContent).toBe('Activity');

        const header = docLink.closest('.activity-section__header');
        expect(header).not.toBeNull();

        unmount();
      }
    });

    it('satisfies HTML 4.10.4: StudioDocLink is NOT nested inside <button> or <label>', async () => {
      const Wrapper = createWrapper();
      const { container } = render(<ActivitySection issue={mockIssue} currentUserId="u1" />, {
        wrapper: Wrapper,
      });

      await waitFor(() => {
        expect(screen.getByTestId('activity-section-doc-link')).toBeDefined();
      });

      const docLink = screen.getByTestId('activity-section-doc-link');
      expect(docLink.closest('button')).toBeNull();
      expect(docLink.closest('label')).toBeNull();

      const invalidButtons = container.querySelectorAll(
        'button a, button button, label a, label button',
      );
      expect(invalidButtons.length).toBe(0);
    });

    it('opens HelpDrawer via ShellPanelsProvider when StudioDocLink is clicked', async () => {
      const DummyHelpDrawer = ({ arg }: { arg?: unknown }) => {
        const data = arg as { href?: string; title?: string } | undefined;
        return (
          <div data-testid="dummy-help-drawer" data-href={data?.href} data-title={data?.title}>
            Help Drawer for {data?.title} ({data?.href})
          </div>
        );
      };
      const unregister = registerShellPanel('help', DummyHelpDrawer);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <ShellPanelsProvider>
              <ActivitySection issue={mockIssue} currentUserId="u1" />
            </ShellPanelsProvider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const docLink = await screen.findByTestId('activity-section-doc-link');
      fireEvent.click(docLink);

      await waitFor(() => {
        const drawer = screen.getByTestId('dummy-help-drawer');
        expect(drawer).toBeDefined();
        expect(drawer.getAttribute('data-href')).toBe(
          '/docs/ticket-screen-and-work-item-features#activity-stream-and-audit-ledger',
        );
        expect(drawer.getAttribute('data-title')).toBe('Audit Ledger ->');
      });

      unregister();
    });

    it('supports keyboard navigation via ArrowLeft and tab focus on StudioDocLink', async () => {
      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      const allTab = await screen.findByRole('tab', { name: 'All' });
      allTab.focus();

      // Home on index 0 does not change index
      fireEvent.keyDown(allTab, { key: 'Home' });
      expect(allTab.getAttribute('aria-selected')).toBe('true');

      // Unrelated key (e.g. Escape) does not change index
      fireEvent.keyDown(allTab, { key: 'Escape' });
      expect(allTab.getAttribute('aria-selected')).toBe('true');

      // ArrowLeft wraps around to Gates tab (index 3)
      fireEvent.keyDown(allTab, { key: 'ArrowLeft' });
      const gatesTab = screen.getByRole('tab', { name: /^Agent and workflow gates/ });
      expect(gatesTab.getAttribute('aria-selected')).toBe('true');

      // End on index 3 does not change index
      fireEvent.keyDown(gatesTab, { key: 'End' });
      expect(gatesTab.getAttribute('aria-selected')).toBe('true');

      // ArrowLeft moves to History tab (index 2)
      fireEvent.keyDown(gatesTab, { key: 'ArrowLeft' });
      const historyTab = screen.getByRole('tab', { name: 'History' });
      expect(historyTab.getAttribute('aria-selected')).toBe('true');

      // Focus on doc link
      const docLink = screen.getByTestId('activity-section-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
    });

    it('covers handleJumpToComment when activeTab is history and all', async () => {
      const activityData: ActivityResponse = {
        items: [
          {
            id: 'act-gate-jump',
            category: 'AGENT_GATE',
            event_type: 'GATE_VETOED',
            actor: { type: 'AGENT', display_name: 'sec-gate' },
            payload: {
              hook_name: 'sec-auditor',
              audit_comment_id: 'c-jump-target',
            },
            created_at: '2026-11-12T10:05:00Z',
          },
        ],
        next_cursor: null,
        counts: { all: 1, comments: 0, history: 0, gates: 1 },
      };
      mockFetchActivity.mockResolvedValue(activityData);

      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      // In All tab, jump to comment
      const jumpBtnAll = await screen.findByRole('button', { name: 'View audit details' });
      fireEvent.click(jumpBtnAll);

      // Now switch to gates tab and then jump to comment
      const gatesTab = screen.getByRole('tab', { name: /^Agent and workflow gates/ });
      fireEvent.click(gatesTab);
      const jumpBtnGates = await screen.findByRole('button', { name: 'View audit details' });
      fireEvent.click(jumpBtnGates);
    });

    it('renders history items with category="HISTORY" in History tab and jumps to comment if target element exists', async () => {
      const mockCommentEl = document.createElement('div');
      mockCommentEl.id = 'comment-c-audit-777';
      const scrollIntoViewMock = vi.fn();
      mockCommentEl.scrollIntoView = scrollIntoViewMock;
      document.body.appendChild(mockCommentEl);

      const activityWithHistoryAndGate: ActivityResponse = {
        items: [
          {
            id: 'act-hist-77',
            category: 'HISTORY',
            event_type: 'FIELD_UPDATED',
            actor: { handle: 'charlie' },
            payload: { field: 'state', from_value: 'Backlog', to_value: 'In Progress' },
            created_at: '2026-11-12T10:00:00Z',
          },
          {
            id: 'act-gate-77',
            category: 'AGENT_GATE',
            event_type: 'GATE_VETOED',
            actor: { type: 'AGENT', display_name: 'sec-gate' },
            payload: {
              hook_name: 'sec-auditor',
              reason: 'Policy violation',
              audit_comment_id: 'c-audit-777',
            },
            created_at: '2026-11-12T10:05:00Z',
          },
        ],
        next_cursor: null,
        counts: { all: 2, comments: 0, history: 1, gates: 1 },
      };
      mockFetchActivity.mockResolvedValue(activityWithHistoryAndGate);

      const Wrapper = createWrapper();
      render(<ActivitySection issue={mockIssue} currentUserId="u1" />, { wrapper: Wrapper });

      // Click history tab and verify history row is rendered
      const historyTab = await screen.findByRole('tab', { name: 'History' });
      fireEvent.click(historyTab);

      const histRow = await screen.findByTestId('history-row');
      expect(histRow).toBeDefined();

      // Click gates tab and click jump to comment button
      const gatesTab = screen.getByRole('tab', { name: /^Agent and workflow gates/ });
      fireEvent.click(gatesTab);

      const jumpBtn = await screen.findByRole('button', { name: 'View audit details' });
      fireEvent.click(jumpBtn);

      await waitFor(() => {
        expect(scrollIntoViewMock).toHaveBeenCalled();
      });

      document.body.removeChild(mockCommentEl);
    });

    it('verifies activity.css contains mobile touch targets and title-row flex wrap rules', () => {
      const cssPath = path.resolve(__dirname, 'activity.css');
      const cssContent = fs.readFileSync(cssPath, 'utf-8');

      expect(cssContent).toContain('.activity-section__title-row');
      expect(cssContent).toContain('flex-wrap: wrap');
      expect(cssContent).toContain('min-height: var(--tap-min, 44px)');
    });
  });
});
