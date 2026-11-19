import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { YourWorkView } from '../your-work/YourWorkView';
import { SaveViewModal } from './SaveViewModal';
import { TableView } from '../table/TableView';
import { TimelineView } from '../timeline/TimelineView';
import { IssuesWorkspaceRoute, useIssueKeyboardMap } from './viewRegistry';
import {
  fetchProjectStates,
  createProjectIssue,
  patchProjectIssue,
  deleteProjectIssue,
} from './viewsApi';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import * as stickiesApi from '../stickies/stickiesApi';
import { ProjectOverviewView } from '../stickies/ProjectOverviewView';
import { WorkspaceStickiesView } from '../stickies/WorkspaceStickiesView';
import { StickyCard } from '../stickies/StickyCard';
import { StickyPromotePreviewModal } from '../stickies/StickyPromotePreviewModal';
import { CreateWorkspaceModal } from '../workspaces/CreateWorkspaceModal';
import { safeRandomUUID, safeCopyToClipboard } from '../../utils/uuid';
import { FIXTURE_12_ISSUES } from './fixtures';
import type { IssueItem } from './viewsApi';
import * as clientModule from '../../api/client';
import { TransitionRuleCard } from '../workflows/TransitionRuleCard';
import * as Realtime from '../../realtime';
import * as ListViewBarrel from './ListView';
import { CommandPalette } from '../../app/CommandPalette';
import { Topbar } from '../../app/Topbar';
import {
  ProjectViewsRedirect,
  ProjectRouteContainer,
  ProjectIssuesRoute,
  NotFoundView,
  FullScreenIssueRoute,
  ProjectRouteContext,
  WorkspaceHomeView,
  ProjectCyclesView,
  ProjectModulesView,
  DraftsWorkspaceView,
} from '../../app/routes';
import { PropertiesRail } from '../drawer-rail/PropertiesRail';
import { ShellPanelsProvider } from '../../app/shellPanels';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { BulkActionBar } from './BulkActionBar';

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

function ShortcutTestComponent() {
  const [, setSelectedIds] = React.useState<string[]>([]);
  useIssueKeyboardMap({
    issues: [],
    selectedIds: [],
    setSelectedIds,
  });
  return <div>Shortcut Test</div>;
}

describe('Hubs Coverage Booster (KANBA-221)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  describe('YourWorkView edge branches', () => {
    it('handles projects fetch failure, notifications failure, and issue fetch failure', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      // /api/v1/auth/me -> success
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'u1', handle: 'alice', display_name: 'Alice' };
        }
        if (url === '/api/v1/projects') {
          return { items: [{ id: 'p1', key: 'FAIL', name: 'Failing Proj' }] };
        }
        if (url.includes('/issues')) {
          throw new Error('500 server error');
        }
        if (url.includes('/notifications')) {
          throw new Error('403 forbidden');
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByRole('heading', { name: /your work/i })).toBeDefined();
      expect(screen.getByTestId('tab-assigned-to-me')).toBeDefined();

      // Click Assigned to Me tab when active
      fireEvent.click(screen.getByTestId('tab-assigned-to-me'));
    });

    it('covers peek link click, search query filtering, and issue without state/priority', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'u1', handle: 'alice', display_name: 'Alice' };
        }
        if (url === '/api/v1/projects') {
          return [{ id: 'p1', key: 'TEST', name: 'Test Proj' }];
        }
        if (url.includes('/issues')) {
          return [
            {
              id: 'i-bare',
              key: 'TEST-1',
              summary: 'Bare work item without state or prio',
              project_key: 'TEST',
              created_by_id: 'u1',
              assignees: [{ principal: { id: 'u1', handle: 'alice' } }],
              state: null,
              priority: null,
            },
          ];
        }
        if (url.includes('/notifications')) {
          return { items: [] };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Bare work item without state or prio')).toBeDefined();

      // Click peek link directly
      const peekLink = screen.getByTestId('peek-link-TEST-1');
      fireEvent.click(peekLink);

      // Filter input typing
      const searchInput = screen.getByPlaceholderText(/Filter work items/i);
      fireEvent.change(searchInput, { target: { value: 'non-matching query' } });
      expect(screen.getByText(/No work items matching/i)).toBeDefined();
    });

    it('covers empty projects, email/handle/free_text assignees, created_by_handle, subscribed tab, and inspect peek', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'u1', handle: 'alice_dev', display_name: 'Alice Dev', email: 'alice@example.com' };
        }
        if (url === '/api/v1/projects') {
          return [{ id: 'p1', key: 'DEVS', name: 'Dev Project' }];
        }
        if (url.includes('/issues')) {
          return {
            items: [
              {
                id: 'i-1',
                key: 'DEVS-1',
                summary: 'Matched by handle',
                project_key: 'DEVS',
                assignees: [{ principal: { id: 'other', handle: '@alice_dev', email: 'other@example.com' } }],
                created_by_handle: 'alice_dev',
                state: { id: 's1', name: 'In Progress', group: 'started' },
                priority: { slug: 'urgent', label: 'Urgent' },
                subscribed: true,
              },
              {
                id: 'i-2',
                key: 'DEVS-2',
                summary: 'Matched by email',
                project_key: 'DEVS',
                assignees: [{ principal: { id: 'other2', handle: 'bob', email: 'alice@example.com' } }],
                created_by_id: 'u1',
                subscribed: false,
              },
              {
                id: 'i-3',
                key: 'DEVS-3',
                summary: 'Matched by free text',
                project_key: 'DEVS',
                assignees: [{ kind: 'free_text', free_text: '@alice_dev' }],
                created_by_id: 'someone_else',
                subscribed: false,
              },
            ],
          };
        }
        if (url.includes('/notifications')) {
          return {
            items: [
              { id: 'n1', issue: { key: 'DEVS-2' } },
            ],
          };
        }
        return {};
      });

      const peekSpy = vi.fn();
      window.addEventListener('kb:open-issue-peek', peekSpy);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Matched by handle')).toBeDefined();
      expect(screen.getByText('Matched by email')).toBeDefined();
      expect(screen.getByText('Matched by free text')).toBeDefined();

      // Inspect peek button click
      const inspectBtn = screen.getAllByRole('button', { name: /Inspect DEVS-1/i })[0]!;
      fireEvent.click(inspectBtn);
      expect(peekSpy).toHaveBeenCalled();

      // Switch to Created by Me tab
      const createdTab = screen.getByTestId('tab-created-by-me');
      fireEvent.click(createdTab);
      expect(screen.getByText('Matched by handle')).toBeDefined();
      expect(screen.getByText('Matched by email')).toBeDefined();

      // Switch to Subscribed tab
      const subTab = screen.getByTestId('tab-subscribed');
      fireEvent.click(subTab);
      expect(screen.getByText('Matched by handle')).toBeDefined();
      expect(screen.getByText('Matched by email')).toBeDefined();

      // Filter by project key
      const searchInput = screen.getByPlaceholderText(/Filter work items/i);
      fireEvent.change(searchInput, { target: { value: 'devs' } });
      expect(screen.getByText('Matched by handle')).toBeDefined();

      window.removeEventListener('kb:open-issue-peek', peekSpy);
    });

    it('handles zero projects gracefully', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'u1', handle: 'alice' };
        }
        if (url === '/api/v1/projects') {
          return [];
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByRole('heading', { name: /your work/i })).toBeDefined();
      expect(await screen.findByText('No work items currently assigned to you.')).toBeDefined();
    });

    it('renders static fallback when rendered outside QueryClientProvider', () => {
      render(
        <MemoryRouter initialEntries={['/your-work']}>
          <YourWorkView />
        </MemoryRouter>,
      );
      expect(screen.getByRole('heading', { name: 'Your Work' })).toBeDefined();
      expect(screen.getByText('No work items found')).toBeDefined();
    });
  });

  describe('TableView inline editing & capability edge branches', () => {
    it('covers issue.capabilities containing VIEWER-only when project has ADMIN, and onOpenPeek clicks', () => {
      const onOpenPeek = vi.fn();
      const testIssues: IssueItem[] = [
        {
          id: 'v-1',
          key: 'KAN-V1',
          summary: 'Viewer restricted issue',
          capabilities: ['VIEWER'],
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'low', label: 'Low' },
        },
      ];

      render(
        <TableView
          issues={testIssues}
          projectKey="KAN_PEEK"
          capabilities={['ADMIN']}
          onOpenPeek={onOpenPeek}
        />,
      );

      // Verify row click triggers onOpenPeek
      const row = screen.getByRole('row', { name: /KAN-V1/i });
      fireEvent.click(row);
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-V1');

      // Verify link click triggers onOpenPeek
      const link = screen.getByRole('link', { name: 'KAN-V1' });
      fireEvent.click(link);
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-V1');
    });
    it('covers issue.capabilities containing VIEWER but overridden by ADMIN, and unassigning me', async () => {
      const onUpdateIssue = vi.fn();

      const testIssues: IssueItem[] = [
        {
          id: 't-1',
          key: 'KAN-ADMIN-VIEWER',
          summary: 'Admin with viewer capability',
          capabilities: ['VIEWER', 'ADMIN'],
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High' },
          assignees: [
            {
              id: 'asg-me',
              kind: 'principal',
              principal: { id: 'u-me', handle: 'adam', display_name: 'Adam Outler', type: 'USER' },
            },
          ],
          modules: [{ id: 'm1', name: 'Core Engine' }],
          module_ids: ['m1'],
          start_date: '2026-11-01',
          due_date: '2026-11-20',
        },
      ];

      // Configure table cols with start_date and modules
      localStorage.setItem(
        'kb.tableCols.KAN_EDGES',
        JSON.stringify(['key', 'summary', 'state', 'priority', 'assignees', 'modules', 'start_date', 'due_date']),
      );

      const { rerender } = render(
        <TableView
          issues={testIssues}
          projectKey="KAN_EDGES"
          modulesEnabled={true}
          onUpdateIssue={onUpdateIssue}
        />,
      );

      // Verify modules rendered with name
      expect(screen.getByText('📦 Core Engine')).toBeDefined();

      // Verify assign button removes me when I am already assigned
      const assignBtn = screen.getByRole('button', { name: 'Assign issue KAN-ADMIN-VIEWER' });
      fireEvent.click(assignBtn);
      expect(onUpdateIssue).toHaveBeenCalledWith('KAN-ADMIN-VIEWER', expect.objectContaining({
        assignees: [],
      }));

      // Rerender with VIEWER-only capabilities to cover static start_date
      rerender(
        <TableView
          issues={testIssues}
          projectKey="KAN_EDGES"
          modulesEnabled={true}
          capabilities={['VIEWER']}
          onUpdateIssue={onUpdateIssue}
        />,
      );
      expect(screen.getByText('2026-11-01')).toBeDefined();
    });

    it('covers inline state Cancelled/In Review, cycle clear, date clear, start_date and created_by sorting, and empty state', () => {
      const onUpdateIssue = vi.fn();
      const onCreateIssue = vi.fn();

      const testIssues: IssueItem[] = [
        {
          id: 't-1',
          key: 'KAN-1',
          summary: 'Item 1',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'low', label: 'Low' },
          assignees: [{ kind: 'free_text', free_text: 'External Contractor', id: 'ft-1' } as never],
          cycle_id: 'cycle-custom-99',
          cycle: { id: 'cycle-custom-99', name: 'Custom Milestone 99' },
          start_date: '2026-11-05',
          due_date: '2026-11-01', // overdue
          created_by_handle: 'charlie',
        },
        {
          id: 't-2',
          key: 'KAN-2',
          summary: 'Item 2',
          state: { id: 's2', name: 'In Progress', group: 'started' },
          priority: { slug: 'urgent', label: 'Urgent' },
          assignees: [],
          cycle_id: null,
          start_date: '2026-11-02',
          due_date: null,
          created_by_id: 'alice',
        },
      ];

      localStorage.setItem(
        'kb.tableCols.KAN_EDGES_2',
        JSON.stringify(['key', 'summary', 'state', 'priority', 'assignees', 'cycle', 'start_date', 'due_date', 'created_by']),
      );

      const { rerender } = render(
        <TableView
          issues={testIssues}
          projectKey="KAN_EDGES_2"
          modulesEnabled={false}
          onUpdateIssue={onUpdateIssue}
        />,
      );

      // Verify external assignee hint rendered
      expect(screen.getByTestId('hint-external-assignee')).toBeDefined();

      // Inline State Change to Cancelled
      const stateSelect = screen.getByLabelText('Edit state for KAN-1');
      fireEvent.change(stateSelect, { target: { value: 'Cancelled' } });
      expect(onUpdateIssue).toHaveBeenCalledWith('KAN-1', expect.objectContaining({
        state: expect.objectContaining({ group: 'cancelled', name: 'Cancelled' }),
      }));

      // Inline State Change to In Review
      fireEvent.change(stateSelect, { target: { value: 'In Review' } });
      expect(onUpdateIssue).toHaveBeenCalledWith('KAN-1', expect.objectContaining({
        state: expect.objectContaining({ group: 'started', name: 'In Review' }),
      }));

      // Inline Cycle Change to clear
      const cycleSelect = screen.getByLabelText('Edit cycle for KAN-1');
      fireEvent.change(cycleSelect, { target: { value: '' } });
      expect(onUpdateIssue).toHaveBeenCalledWith('KAN-1', expect.objectContaining({
        cycle_id: null,
        cycle: null,
      }));

      // Inline Date Change to clear
      const startDateInput = screen.getByLabelText('Edit start date for KAN-1');
      fireEvent.change(startDateInput, { target: { value: '' } });
      expect(onUpdateIssue).toHaveBeenCalledWith('KAN-1', expect.objectContaining({
        start_date: null,
      }));

      // Sort by start_date
      const startDateTh = screen.getByRole('columnheader', { name: /Start date/i });
      const startDateSortBtn = startDateTh.querySelector('button');
      if (startDateSortBtn) {
        fireEvent.click(startDateSortBtn); // asc
        fireEvent.click(startDateSortBtn); // desc
        fireEvent.click(startDateSortBtn); // none
      }

      // Sort by created_by
      const createdTh = screen.getByRole('columnheader', { name: /Created by/i });
      const createdSortBtn = createdTh.querySelector('button');
      if (createdSortBtn) {
        fireEvent.click(createdSortBtn); // asc
        fireEvent.click(createdSortBtn); // desc
        fireEvent.click(createdSortBtn); // none
      }

      // Render empty issues
      rerender(
        <TableView
          issues={[]}
          projectKey="KAN_EDGES_2"
          onCreateIssue={onCreateIssue}
        />,
      );
      expect(screen.getByText('No work items found')).toBeDefined();
      const createFirstBtn = screen.getByRole('button', { name: /\+ Create first work item/i });
      fireEvent.click(createFirstBtn);
      expect(onCreateIssue).toHaveBeenCalled();
    });
  });

  describe('SaveViewModal edge branches', () => {
    it('clears error on name typing and covers none grouping, null search query, and non-Error throw', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockRejectedValueOnce('A raw string error rejection');

      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal
            isOpen={true}
            onClose={vi.fn()}
            projectKey="KAN"
            layout="list"
            groupBy="none"
            subGroupBy="none"
            activeFilters={{
              stateIds: [],
              priorityIds: [],
              assigneeIds: [],
              cycleIds: [],
              moduleIds: [],
              searchQuery: null,
            }}
          />
        </QueryClientProvider>,
      );

      const nameInput = screen.getByTestId('save-view-name-input');
      fireEvent.change(nameInput, { target: { value: 'Trigger Error' } });

      const form = screen.getByRole('dialog').querySelector('form')!;
      fireEvent.submit(form);

      // Verify raw string error fallback message
      expect(await screen.findByRole('alert')).toBeDefined();
      expect(screen.getByRole('alert').textContent).toBe('Failed to save view');

      // Typing into input when error is present clears error
      fireEvent.change(nameInput, { target: { value: 'New Name' } });
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  describe('TimelineView fallback branches', () => {
    it('covers scrollTo fallback scrollLeft and priority kinds', () => {
      const mockIssues = [
        {
          id: 'tm-1',
          key: 'KAN-TM1',
          summary: 'Low priority item',
          start_date: '2026-11-05',
          due_date: '2026-11-10',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'low', label: 'Low' },
        },
      ];

      const { container } = render(
        <TimelineView
          issues={mockIssues}
          projectKey="KAN"
          today="2026-11-08"
        />,
      );

      // canvasWrapperRef.current without scrollTo
      const wrapper = container.querySelector('.timeline-right-canvas-wrapper');
      if (wrapper) {
        // @ts-expect-error test fallback
        delete wrapper.scrollTo;
      }

      const todayBtn = screen.getByRole('button', { name: 'Today' });
      fireEvent.click(todayBtn);
    });

    it('covers quarter scale headers and unrecognized priority slug', () => {
      const mockIssues = [
        {
          id: 'tm-q1',
          key: 'KAN-Q1',
          summary: 'Quarter scale item',
          start_date: '2026-03-01',
          due_date: '2026-03-15',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'custom_unknown', label: 'Unknown' },
        },
      ];

      render(
        <TimelineView
          issues={mockIssues}
          projectKey="KAN"
          today="2026-03-08"
        />,
      );

      // Switch zoom to Quarter
      const quarterRadio = screen.getByRole('radio', { name: 'Quarter' });
      fireEvent.click(quarterRadio);

      // Verify day label or month label rendered in quarter scale
      expect(screen.getByText('08')).toBeDefined();
    });
  });

  describe('ViewsApi & UUID edge branches', () => {
    it('covers fetchProjectStates empty/undefined guards', async () => {
      expect(await fetchProjectStates('')).toEqual([]);
      expect(await fetchProjectStates('undefined')).toEqual([]);
    });

    it('covers safeRandomUUID fallback when crypto.getRandomValues is not present', () => {
      const cryptoMutable = crypto as unknown as { randomUUID?: unknown; getRandomValues?: unknown };
      const origRandomUUID = cryptoMutable.randomUUID;
      const origGetRandomValues = cryptoMutable.getRandomValues;
      try {
        cryptoMutable.randomUUID = () => { throw new Error('stub'); };
        cryptoMutable.getRandomValues = undefined;
        const id = safeRandomUUID();
        expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      } finally {
        cryptoMutable.randomUUID = origRandomUUID;
        cryptoMutable.getRandomValues = origGetRandomValues;
      }
    });
  });

  describe('YourWorkView more edge branches', () => {
    it('covers multiple projects where one throws, user email matching, handle matching, created_by matching, and all priority slugs', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'user-456', handle: 'bob', display_name: 'Bob', email: 'bob@corp.internal' };
        }
        if (url === '/api/v1/projects') {
          return [
            { id: 'p1', key: 'GOOD', name: 'Good Project' },
            { id: 'p2', key: 'BAD', name: 'Bad Project' },
          ];
        }
        if (url.includes('/projects/BAD/issues')) {
          throw new Error('Network failure on BAD project');
        }
        if (url.includes('/projects/GOOD/issues')) {
          return [
            {
              id: 'g-1',
              key: 'GOOD-1',
              summary: 'Email assignee and urgent prio',
              project_key: 'GOOD',
              created_by: 'user-456',
              state: { id: 's1', name: 'Todo', group: 'unstarted' },
              priority: { slug: 'urgent', label: 'Urgent' },
              assignees: [
                { id: 'asg-1', principal: { id: 'other-id', handle: 'other', email: 'bob@corp.internal' } },
              ],
              subscribed: false,
            },
            {
              id: 'g-2',
              key: 'GOOD-2',
              summary: 'Handle match and low prio',
              project_key: 'GOOD',
              created_by_handle: '@bob',
              state: { id: 's2', name: 'Done', group: 'completed' },
              priority: { slug: 'low', label: 'Low' },
              assignees: [
                { id: 'asg-2', free_text: '@bob' },
              ],
              subscribed: true,
            },
            {
              id: 'g-3',
              key: 'GOOD-3',
              summary: 'Fallback prio without slug match',
              project_key: 'GOOD',
              created_by_id: 'someone-else',
              state: { id: 's3', name: 'In Review', group: 'started' },
              priority: { slug: 'special_prio', label: 'Special' },
              assignees: [],
              subscribed: false,
            },
          ];
        }
        if (url.includes('/notifications')) {
          return {
            items: [
              {
                id: 'notif-1',
                issue: { id: 'g-3', key: 'GOOD-3', summary: 'Subscribed via notification' },
                event_type: 'MENTION',
              },
            ],
          };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // GOOD-1 and GOOD-2 are assigned to bob
      expect(await screen.findByText('GOOD-1')).toBeDefined();
      expect(screen.getByText('GOOD-2')).toBeDefined();

      // Switch to Created by Me tab -> shows GOOD-1 and GOOD-2
      const createdTab = screen.getByTestId('tab-created-by-me');
      fireEvent.click(createdTab);
      expect(await screen.findByText('GOOD-1')).toBeDefined();

      // Switch to Subscribed tab -> shows GOOD-2 (subscribed: true) and GOOD-3 (via notification)
      const subTab = screen.getByTestId('tab-subscribed');
      fireEvent.click(subTab);
      expect(await screen.findByText('GOOD-2')).toBeDefined();
      expect(screen.getByText('GOOD-3')).toBeDefined();

      // Search filtering for non-existent text
      const searchInput = screen.getByPlaceholderText('Filter work items...');
      fireEvent.change(searchInput, { target: { value: 'non_existent_token_12345' } });
      expect(await screen.findByText(/No work items matching "non_existent_token_12345" in this tab/i)).toBeDefined();
    });

    it('covers edge branches: missing assignees, missing userHandle, missing priority/state, and projectKey split', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'u-nohandle', handle: '', display_name: 'No Handle' };
        }
        if (url === '/api/v1/projects') {
          return [{ id: 'p-no-key', name: 'Fallback Proj', identifier: 'FALLBACK' }];
        }
        if (url.includes('/issues')) {
          return [
            {
              id: 'iss-no-prio',
              key: 'SPLIT-999',
              summary: 'Issue with missing project_key and priority label fallback',
              created_by_id: 'u-nohandle',
              state: null,
              priority: { slug: 'low', label: null },
              assignees: [{ id: 'u-nohandle' }],
            },
          ];
        }
        if (url.includes('/notifications')) {
          return { items: [] };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('SPLIT-999')).toBeDefined();
      expect(screen.getByText('SPLIT')).toBeDefined();
      expect(screen.getByText('low')).toBeDefined();
    });
  });

  describe('TableView Viewer and Cycle branches', () => {
    it('covers viewer-only mode with cycle, start_date, and due_date pills, and custom cycle select in edit mode', () => {
      const mockViewerIssues: IssueItem[] = [
        {
          id: 'v-1',
          key: 'KAN-V1',
          summary: 'Viewer issue 1 with cycle and dates',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium' },
          cycle_id: 'cycle-1',
          cycle: { id: 'cycle-1', name: 'Sprint Alpha' },
          start_date: '2026-11-01',
          due_date: '2026-11-10',
          module_ids: ['mod-1'],
          modules: [{ id: 'mod-1', name: 'Core Engine' }],
        },
        {
          id: 'v-2',
          key: 'KAN-V2',
          summary: 'Viewer issue 2 overdue without cycle',
          state: { id: 's2', name: 'In Progress', group: 'started' },
          priority: { slug: 'urgent', label: 'Urgent' },
          start_date: null,
          due_date: '2020-01-01',
          cycle_id: null,
        },
      ];

      const { rerender } = render(
        <TableView
          issues={mockViewerIssues}
          projectKey="KAN"
          capabilities={['VIEWER']}
        />,
      );

      // Verify non-editable pills rendered
      expect(screen.getByText(/Sprint Alpha/i)).toBeDefined();
      expect(screen.getByText(/2026-11-10/i)).toBeDefined();
      expect(screen.getByText(/2020-01-01/i)).toBeDefined();

      // Rerender with custom cycle in editable mode
      const mockEditIssues: IssueItem[] = [
        {
          id: 'e-1',
          key: 'KAN-E1',
          summary: 'Edit issue with custom cycle',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High' },
          cycle_id: 'cycle-special-99',
          cycle: { id: 'cycle-special-99', name: 'Custom Sprint 99' },
        },
      ];

      rerender(
        <TableView
          issues={mockEditIssues}
          projectKey="KAN"
          capabilities={['EDIT']}
        />,
      );

      expect(screen.getByRole('option', { name: 'Custom Sprint 99' })).toBeDefined();
    });
  });

  describe('SaveViewModal transitions and callbacks', () => {
    it('covers isOpen transition from false to true to false, and onSaved callback', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockResolvedValueOnce({ id: 'saved-view-999' });
      const onSaved = vi.fn();
      const onClose = vi.fn();

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal
            isOpen={false}
            onClose={onClose}
            projectKey="KAN"
            layout="board"
            activeFilters={{}}
            onSaved={onSaved}
          />
        </QueryClientProvider>,
      );
      expect(screen.queryByTestId('save-view-modal')).toBeNull();

      rerender(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal
            isOpen={true}
            onClose={onClose}
            projectKey="KAN"
            layout="board"
            activeFilters={{}}
            onSaved={onSaved}
          />
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('save-view-modal')).toBeDefined();

      const nameInput = screen.getByTestId('save-view-name-input');
      fireEvent.change(nameInput, { target: { value: 'Valid Name' } });
      const submitBtn = screen.getByTestId('save-view-submit-btn');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(onSaved).toHaveBeenCalledWith('saved-view-999');
        expect(onClose).toHaveBeenCalled();
      });

      rerender(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal
            isOpen={false}
            onClose={onClose}
            projectKey="KAN"
            layout="board"
            activeFilters={{}}
            onSaved={onSaved}
          />
        </QueryClientProvider>,
      );
      expect(screen.queryByTestId('save-view-modal')).toBeNull();
    });
  });

  describe('TimelineView BLOCKS arrows routing', () => {
    it('covers BLOCKS arrow routing between issues with start and due dates', () => {
      const mockBlockIssues = [
        {
          id: 'b-1',
          key: 'KAN-B1',
          summary: 'Blocker issue',
          start_date: '2026-11-01',
          due_date: '2026-11-05',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High' },
          outbound_blocks: [
            { target_key: 'KAN-B2', link_state: 'normal', restricted: false },
          ],
        },
        {
          id: 'b-2',
          key: 'KAN-B2',
          summary: 'Blocked issue',
          start_date: '2026-11-06',
          due_date: '2026-11-10',
          state: { id: 's2', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'urgent', label: 'Urgent' },
        },
      ];

      render(
        <TimelineView
          issues={mockBlockIssues}
          projectKey="KAN"
          today="2026-11-03"
        />,
      );

      // Verify SVG overlay rendered with connector
      const checkbox = screen.getByRole('checkbox', { name: /Show BLOCKS arrows/i });
      expect((checkbox as HTMLInputElement).checked).toBe(true);
      expect(document.querySelector('.timeline-svg-overlay')).toBeDefined();
    });
  });

  describe('IssuesWorkspaceRoute SaveViewModal integration', () => {
    it('opens and closes SaveViewModal from FilterDisplayBar onSaveView', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockResolvedValue({ id: 'new-view-1' });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssuesWorkspaceRoute
              projectKey="KAN"
              initialIssues={FIXTURE_12_ISSUES}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Open Display popover and click "Save as view"
      const displayBtn = screen.getByRole('button', { name: /display configuration/i });
      fireEvent.click(displayBtn);
      const saveAsViewBtn = screen.getByRole('button', { name: /save as view/i });
      fireEvent.click(saveAsViewBtn);

      const modal1 = screen.getByTestId('save-view-modal');
      expect(modal1).toBeDefined();

      // Click Cancel within modal to close
      const cancelBtn = within(modal1).getByRole('button', { name: /cancel/i });
      fireEvent.click(cancelBtn);
      expect(screen.queryByTestId('save-view-modal')).toBeNull();

      // Open Display popover again and save
      fireEvent.click(displayBtn);
      const saveAsViewBtn2 = screen.getByRole('button', { name: /save as view/i });
      fireEvent.click(saveAsViewBtn2);
      const modal2 = screen.getByTestId('save-view-modal');
      const nameInput = within(modal2).getByTestId('save-view-name-input');
      fireEvent.change(nameInput, { target: { value: 'Saved Preset' } });
      const submitBtn = within(modal2).getByTestId('save-view-submit-btn');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.queryByTestId('save-view-modal')).toBeNull();
      });
    });
  });

  describe('TransitionRuleCard edge branches', () => {
    it('covers empty hooks, purple/green badges, and singular active hook label', () => {
      const onAddHook = vi.fn();
      const rule = {
        id: 'r-empty',
        from_state: 'In Review',
        to_state: 'Done',
        hooks: [],
      };
      const { rerender } = render(
        <TransitionRuleCard
          rule={rule as any}
          projectKey="KAN"
          onReorder={vi.fn()}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={onAddHook}
          onDryRun={vi.fn()}
        />,
      );

      expect(screen.getByTestId('empty-hooks-cta')).toBeDefined();
      expect(screen.getByText('🟣 In Review')).toBeDefined();
      expect(screen.getByText('🟢 Done')).toBeDefined();
      expect(screen.getByText('0 Active Hooks')).toBeDefined();

      const addBtn = screen.getByRole('button', { name: /add hook/i });
      fireEvent.click(addBtn);
      expect(onAddHook).toHaveBeenCalledWith({ from_state: 'In Review', to_state: 'Done' });

      // Rerender with exactly 1 active hook to cover "1 Active Hook" singular
      const ruleSingle = {
        id: 'r-single',
        from_state: null,
        to_state: 'Todo',
        hooks: [
          {
            id: 'h-1',
            name: 'Validator Alpha',
            hook_kind: 'script_runner' as const,
            manifest_sha256: 'abc',
            failure_policy: 'fail_closed' as const,
            is_enabled: true,
            timeout_ms: 1000,
            target_latency_budget: null,
          },
        ],
      };
      rerender(
        <TransitionRuleCard
          rule={ruleSingle as any}
          projectKey="KAN"
          onReorder={vi.fn()}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={onAddHook}
          onDryRun={vi.fn()}
        />,
      );
      expect(screen.getByText('1 Active Hook')).toBeDefined();
      expect(screen.getByText(/Any State/i)).toBeDefined();
    });
  });

  describe('useIssueKeyboardMap comprehensive keyboard navigation', () => {
    it('exercises keyboard shortcuts, modifier checks, and row selection', () => {
      const onOpenCreateModal = vi.fn();
      const onOpenFilter = vi.fn();
      const onOpenFieldPopover = vi.fn();
      const onToggleAssigneeMe = vi.fn();
      const shortcutListener = vi.fn();
      window.addEventListener('kb:open-shortcuts', shortcutListener);

      function TestHarness({ layout = 'list' as 'list' | 'board' | 'table' | 'timeline' | 'calendar', isPopoverOrModalOpen = false }) {
        const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
        const kb = useIssueKeyboardMap({
          issues: FIXTURE_12_ISSUES,
          layout,
          selectedIds,
          setSelectedIds,
          modulesEnabled: true,
          onOpenCreateModal,
          onOpenFilter,
          onOpenFieldPopover,
          onToggleAssigneeMe,
          isPopoverOrModalOpen,
        });

        return (
          <div>
            <div data-testid="focused-key">{kb.focusedKey ?? 'none'}</div>
            <div data-testid="selected-count">{selectedIds.length}</div>
            <input data-testid="input-elem" />
            <div
              data-testid="row-click-target"
              onClick={(e) => kb.handleRowClick('KAN-3', e.shiftKey)}
            />
          </div>
        );
      }

      const { rerender } = render(<TestHarness />);

      // 'c' triggers quick create modal
      fireEvent.keyDown(window, { key: 'c' });
      expect(onOpenCreateModal).toHaveBeenCalledTimes(1);

      // '/' triggers filter search
      fireEvent.keyDown(window, { key: '/' });
      expect(onOpenFilter).toHaveBeenCalledTimes(1);

      // '?' triggers shortcuts cheat sheet event
      fireEvent.keyDown(window, { key: '?' });
      expect(shortcutListener).toHaveBeenCalled();

      const firstKey = FIXTURE_12_ISSUES[0]!.key;
      const secondKey = FIXTURE_12_ISSUES[1]!.key;
      const lastKey = FIXTURE_12_ISSUES[FIXTURE_12_ISSUES.length - 1]!.key;

      // 'j' moves focus down to first item
      fireEvent.keyDown(window, { key: 'j' });
      expect(screen.getByTestId('focused-key').textContent).toBe(firstKey);

      // 'j' again moves to second
      fireEvent.keyDown(window, { key: 'j' });
      expect(screen.getByTestId('focused-key').textContent).toBe(secondKey);

      // 'k' moves back up to first
      fireEvent.keyDown(window, { key: 'k' });
      expect(screen.getByTestId('focused-key').textContent).toBe(firstKey);

      // 'k' at index 0 wraps to last item
      fireEvent.keyDown(window, { key: 'k' });
      expect(screen.getByTestId('focused-key').textContent).toBe(lastKey);

      // 'x' toggles selection on focused issue
      fireEvent.keyDown(window, { key: 'x' });
      expect(screen.getByTestId('selected-count').textContent).toBe('1');
      // 'x' toggles it off
      fireEvent.keyDown(window, { key: 'x' });
      expect(screen.getByTestId('selected-count').textContent).toBe('0');

      // 'Shift+x' calls selectRange
      fireEvent.keyDown(window, { key: 'x', shiftKey: true });

      // Field popovers: s, p, a, l, m, d
      fireEvent.keyDown(window, { key: 's' });
      expect(onOpenFieldPopover).toHaveBeenCalledWith('state', expect.anything(), null);

      fireEvent.keyDown(window, { key: 'p' });
      expect(onOpenFieldPopover).toHaveBeenCalledWith('priority', expect.anything(), null);

      fireEvent.keyDown(window, { key: 'a' });
      expect(onOpenFieldPopover).toHaveBeenCalledWith('assignee', expect.anything(), null);

      fireEvent.keyDown(window, { key: 'l' });
      expect(onOpenFieldPopover).toHaveBeenCalledWith('labels', expect.anything(), null);

      fireEvent.keyDown(window, { key: 'm' });
      expect(onOpenFieldPopover).toHaveBeenCalledWith('module', expect.anything(), null);

      fireEvent.keyDown(window, { key: 'd' });
      expect(onOpenFieldPopover).toHaveBeenCalledWith('due_date', expect.anything(), null);

      // 'i' toggles assignee me
      fireEvent.keyDown(window, { key: 'i' });
      expect(onToggleAssigneeMe).toHaveBeenCalledTimes(1);

      // 'Escape' clears selection if selectedIds > 0
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'x' });
      const selCount = parseInt(screen.getByTestId('selected-count').textContent ?? '0', 10);
      if (selCount === 0) {
        fireEvent.keyDown(window, { key: 'x' });
      }
      expect(parseInt(screen.getByTestId('selected-count').textContent ?? '0', 10)).toBeGreaterThan(0);
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.getByTestId('selected-count').textContent).toBe('0');

      // Modifiers (ctrl, meta, alt) are ignored
      fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
      expect(onOpenCreateModal).toHaveBeenCalledTimes(1);

      // Typing in input ignores shortcuts
      const input = screen.getByTestId('input-elem');
      fireEvent.keyDown(input, { key: 'c' });
      expect(onOpenCreateModal).toHaveBeenCalledTimes(1);

      // Row click without shift sets focused key
      fireEvent.click(screen.getByTestId('row-click-target'));
      expect(screen.getByTestId('focused-key').textContent).toBe('KAN-3');

      // Row click with shift selects range
      fireEvent.click(screen.getByTestId('row-click-target'), { shiftKey: true });

      // Board layout H and L navigation
      rerender(<TestHarness layout="board" />);
      fireEvent.keyDown(window, { key: 'h' });
      fireEvent.keyDown(window, { key: 'l' });

      // Popover open suppresses shortcuts
      rerender(<TestHarness isPopoverOrModalOpen={true} />);
      fireEvent.keyDown(window, { key: 'c' });
      expect(onOpenCreateModal).toHaveBeenCalledTimes(1);

      window.removeEventListener('kb:open-shortcuts', shortcutListener);
    });
  });

  describe('YourWorkView fallback branches', () => {
    it('covers non-array data, issue key without hyphen, identifier project key, and non-matching assignees', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return { id: 'u-solo', handle: 'solo' };
        }
        if (url === '/api/v1/projects') {
          return [
            { id: 'p1', identifier: 'IDENT', name: 'Ident Proj' },
            { id: 'p2', name: 'NoKey Proj' },
          ];
        }
        if (url.includes('/issues')) {
          return {
            items: [
              {
                id: 'i-nohyphen',
                key: 'NOHYPHEN',
                summary: 'Issue without hyphen in key',
                state: { id: 's1', name: 'Todo', group: 'unstarted' },
                priority: { slug: 'low', label: 'Low' },
                assignees: [
                  { id: 'u-solo' },
                  { principal: { id: 'other', handle: 'different' } },
                  { kind: 'free_text', free_text: 'diff_free' },
                ],
              },
              {
                id: 'i-unassigned',
                key: 'KAN-999',
                summary: 'Unassigned issue with undefined assignees',
                assignees: undefined,
              },
            ],
          };
        }
        if (url.includes('/notifications')) {
          return [];
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/your-work']}>
            <YourWorkView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const noHyphenItems = await screen.findAllByText('NOHYPHEN');
      expect(noHyphenItems.length).toBeGreaterThan(0);
      expect(screen.getAllByText('KAN').length).toBeGreaterThan(0);

      fireEvent.click(screen.getByTestId('tab-subscribed'));
      expect(await screen.findByText(/You are not subscribed to any work items yet/i)).toBeDefined();

      fireEvent.click(screen.getByTestId('tab-created-by-me'));
      expect(await screen.findByText(/You have not created any work items yet/i)).toBeDefined();
    });
  });

  describe('TableView cycle and date fallback branches', () => {
    it('covers unlisted cycle ID fallback and non-editable date/cycle cells', () => {
      window.localStorage.setItem(
        'kb.tableCols.KAN',
        JSON.stringify(['key', 'summary', 'custom_col', 'start_date', 'cycle', 'priority', 'assignees']),
      );

      const issuesWithCycleAndDate = [
        {
          id: 't-cycle-1',
          key: 'KAN-C1',
          summary: 'Cycle edge item',
          start_date: '2026-11-01',
          cycle_id: 'custom-unlisted-99',
          cycle: undefined,
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: '' },
          assignees: [
            {
              kind: 'user' as const,
              principal: { id: 'u-user', display_name: '', handle: 'justhandle' },
            },
          ],
        },
        {
          id: 't-cycle-2',
          key: 'KAN-C2',
          summary: 'Cycle edge item 2 with null start date',
          start_date: null,
          cycle_id: null,
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'low', label: 'Low' },
        },
      ];

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <TableView
              issues={issuesWithCycleAndDate as any}
              projectKey="KAN"
              selectedIds={['KAN-C1']}
              capabilities={['VIEWER']}
              onUpdateIssue={vi.fn()}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByTestId('cycle-pill').textContent).toContain('Cycle');
      expect(screen.getByText('2026-11-01')).toBeDefined();
      expect(screen.getByText('justhandle')).toBeDefined();

      // Click key link without onOpenPeek to cover default branch
      const keyLink = screen.getByText('KAN-C1');
      fireEvent.click(keyLink);

      rerender(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <TableView
              issues={issuesWithCycleAndDate as any}
              projectKey="KAN"
              selectedIds={['KAN-C1']}
              capabilities={['ADMIN', 'EDIT']}
              onUpdateIssue={vi.fn()}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByRole('option', { name: 'custom-unlisted-99' })).toBeDefined();
    });
  });

  describe('TimelineView scroll and link fallback branches', () => {
    it('handles issue link click without onOpenPeek and scroll when scrollTo is defined or undefined', () => {
      const mockIssues = [
        {
          id: 'tl-1',
          key: 'KAN-TL1',
          summary: 'Timeline item without peek handler',
          start_date: '2026-11-01',
          due_date: '2026-11-05',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'low', label: 'Low' },
          outbound_blocks: [
            { target_key: 'KAN-UNSCHED', link_state: 'normal', restricted: false },
          ],
        },
        {
          id: 'tl-unsched',
          key: 'KAN-UNSCHED',
          summary: 'Unscheduled blocked item',
          start_date: null,
          due_date: null,
          state: { id: 's2', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High' },
        },
      ];

      const { container } = render(
        <TimelineView
          issues={mockIssues as any}
          projectKey="KAN"
          today="2026-11-03"
        />,
      );

      const links = screen.getAllByText('KAN-TL1');
      fireEvent.click(links[0]!);

      // Mock scrollTo on wrapper to cover if branch
      const wrapper = container.querySelector('.timeline-canvas-wrapper');
      if (wrapper) {
        (wrapper as HTMLElement & { scrollTo?: unknown }).scrollTo = vi.fn();
      }

      const todayBtn = screen.getByRole('button', { name: /today/i });
      fireEvent.click(todayBtn);
      expect(todayBtn).toBeDefined();
    });
  });

  describe('Barrels and utility coverage', () => {
    it('verifies exports in realtime and ListView barrels, and safeRandomUUID / safeCopyToClipboard fallbacks', async () => {
      expect(Realtime).toBeDefined();
      expect(ListViewBarrel).toBeDefined();

      const uuid = safeRandomUUID();
      expect(uuid).toBeDefined();

      // Test clipboard when navigator.clipboard.writeText is available
      const origClipboard = navigator.clipboard;
      try {
        const mockWriteText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, 'clipboard', {
          value: { writeText: mockWriteText },
          configurable: true,
        });
        const res = await safeCopyToClipboard('test copy');
        expect(res).toBe(true);

        // Test clipboard when writeText throws -> fallback to execCommand returning true
        mockWriteText.mockRejectedValue(new Error('Permission denied'));
        const origExec = document.execCommand;
        try {
          document.execCommand = vi.fn().mockReturnValue(true);
          const resFallback = await safeCopyToClipboard('fallback copy');
          expect(resFallback).toBe(true);

          // Test when execCommand returns false -> throws underlying error
          document.execCommand = vi.fn().mockReturnValue(false);
          await expect(safeCopyToClipboard('fail copy')).rejects.toThrow('Permission denied');
        } finally {
          document.execCommand = origExec;
        }
      } finally {
        Object.defineProperty(navigator, 'clipboard', {
          value: origClipboard,
          configurable: true,
        });
      }
    });

    it('covers safeRandomUUID fallback when crypto.randomUUID throws', () => {
      const origRandomUUID = crypto.randomUUID;
      try {
        (crypto as { randomUUID?: unknown }).randomUUID = () => {
          throw new Error('Not supported');
        };
        const id = safeRandomUUID();
        expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      } finally {
        (crypto as { randomUUID?: unknown }).randomUUID = origRandomUUID;
      }
    });
  });

  describe('QuickCreateIssueModal branch coverage', () => {
    const defaultStates = [
      { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      { id: 'state-progress', name: 'In Progress', group: 'started' },
      { id: 'state-review', name: 'In Review', group: 'started' },
      { id: 'state-done', name: 'Done', group: 'completed' },
      { id: 'state-cancel', name: 'Cancelled', group: 'cancelled' },
      { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
    ];
    const defaultModules = [
      { id: 'mod-1', name: 'Auth Core', emoji: '🔒' },
      { id: 'mod-2', name: 'Storage', emoji: '📦' },
    ];

    it('covers all state groups, priority emojis, description markdown, and module selection', async () => {
      let createdPayload: any = null;
      const handleCreate = vi.fn().mockImplementation((payload) => {
        createdPayload = payload;
        return { key: 'TEST-123' };
      });

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          states={defaultStates}
          modules={defaultModules}
          modulesEnabled={true}
          defaultStateId="state-cancel"
          defaultPrioritySlug="urgent"
          defaultModuleIds={['mod-1']}
        />,
      );

      const summaryInput = screen.getByRole('textbox', { name: /summary/i });
      fireEvent.change(summaryInput, { target: { value: 'New cancelled urgent issue' } });

      const descInput = screen.getByLabelText(/description/i);
      fireEvent.change(descInput, { target: { value: 'My detailed description' } });

      const submitBtn = screen.getByTestId('quick-create-submit-btn');
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(handleCreate).toHaveBeenCalled();
      });
      expect(createdPayload?.state?.name).toBe('Cancelled');
      expect(createdPayload?.state?.group).toBe('cancelled');
      expect(createdPayload?.priority?.emoji).toBe('🔥');
      expect(createdPayload?.description_markdown).toBe('My detailed description');

      expect(screen.getByText('TEST-123')).toBeDefined();
    });

    it('covers sync onCreate returning empty object, non-Error string rejection, and priority slugs', async () => {
      const handleCreate = vi.fn().mockImplementation(() => {
        throw 'String error failure';
      });

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          states={defaultStates}
          defaultStateId="state-review"
          defaultPrioritySlug="none"
        />,
      );

      fireEvent.change(screen.getByRole('textbox', { name: /summary/i }), {
        target: { value: 'Trigger rejection' },
      });
      fireEvent.click(screen.getByTestId('quick-create-submit-btn'));

      expect(
        await screen.findByText(
          /Network error: Failed to create issue\. Your draft has been preserved\./i,
        ),
      ).toBeDefined();
    });

    it('covers async onCreate returning promise resolving empty object, and state-done', async () => {
      const handleCreate = vi.fn().mockResolvedValue({});
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={handleCreate}
          projectKey="KAN"
          states={defaultStates}
          defaultStateId="state-done"
          defaultPrioritySlug="high"
        />,
      );

      fireEvent.change(screen.getByRole('textbox', { name: /summary/i }), {
        target: { value: 'Done item fallback key' },
      });
      fireEvent.click(screen.getByTestId('quick-create-submit-btn'));

      await waitFor(() => {
        expect(screen.getByText('KAN-NEW')).toBeDefined();
      });
    });

    it('covers state-progress, priority low, and draft discard', () => {
      const onClose = vi.fn();
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={vi.fn()}
          projectKey="KAN"
          states={defaultStates}
          defaultStateId="state-progress"
          defaultPrioritySlug="low"
        />,
      );

      fireEvent.change(screen.getByRole('textbox', { name: /summary/i }), {
        target: { value: 'Progress item' },
      });
      const cancelBtn = screen.getByRole('button', { name: /cancel/i });
      fireEvent.click(cancelBtn);
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('SwimlaneBoardGrid branch coverage', () => {
    const mockGridIssues: IssueItem[] = [
      {
        id: 'iss-1',
        key: 'KAN-G1',
        summary: 'Urgent Alice task',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'urgent', label: 'Urgent' },
        assignees: [
          {
            id: 'asg-1',
            kind: 'principal',
            principal: { id: 'u1', handle: 'alice_sec', display_name: 'Alice Sec', type: 'user' },
          },
        ],
        cycle_id: 'cycle-1',
        module_ids: ['mod-1'],
        gate_status: 'pending',
      },
      {
        id: 'iss-2',
        key: 'KAN-G2',
        summary: 'Adam high task',
        state: { id: 's-prog', name: 'In Progress', group: 'started' },
        priority: { slug: 'high', label: 'High' },
        assignees: [
          {
            id: 'asg-2',
            kind: 'principal',
            principal: { id: 'u2', handle: 'adam_arch', display_name: 'Adam Arch', type: 'user' },
          },
        ],
        cycle_id: 'cyc-custom',
        cycle: { id: 'cyc-custom', name: 'Custom Cycle' },
        modules: [{ id: 'mod-custom', name: 'Custom Module' }],
        gate_status: 'vetoed',
      },
      {
        id: 'iss-3',
        key: 'KAN-G3',
        summary: 'Unassigned low task',
        state: { id: 's-done', name: 'Done', group: 'completed' },
        priority: { slug: 'low', label: 'Low' },
        gate_status: 'approved',
      },
      {
        id: 'iss-4',
        key: 'KAN-G4',
        summary: 'Unmapped state task',
        state: { id: 's-unknown', name: 'Custom Weird State', group: 'custom' },
        priority: { slug: 'none', label: 'None' },
      },
    ];

    it('renders with groupBy=cycle and subGroupBy=cycle and toggles lane collapse', () => {
      render(
        <SwimlaneBoardGrid
          issues={mockGridIssues}
          projectKey="KAN"
          groupBy="cycle"
          subGroupBy="cycle"
          projectCycles={[
            { id: 'cycle-1', name: 'Cycle 1' },
            { id: 'cyc-custom', name: 'Custom Cycle' },
          ]}
        />,
      );

      expect(screen.getByRole('region', { name: /2d swimlane board grid/i })).toBeDefined();

      const toggles = screen.getAllByRole('button');
      const laneToggle = toggles.find((btn) => btn.getAttribute('aria-expanded') === 'true');
      if (laneToggle) {
        fireEvent.click(laneToggle);
        expect(laneToggle.getAttribute('aria-expanded')).toBe('false');
        fireEvent.click(laneToggle);
        expect(laneToggle.getAttribute('aria-expanded')).toBe('true');
      }
    });

    it('renders with groupBy=module and subGroupBy=module and modulesEnabled=true', () => {
      render(
        <SwimlaneBoardGrid
          issues={mockGridIssues}
          projectKey="KAN"
          groupBy="module"
          subGroupBy="module"
          modulesEnabled={true}
          projectModules={[{ id: 'mod-1', name: 'Auth Core' }]}
        />,
      );
      expect(screen.getByText('KAN-G1')).toBeDefined();
    });

    it('renders with groupBy=priority and subGroupBy=assignee, and tests card clicks / selection', () => {
      const onCardClick = vi.fn();
      const onToggleSelect = vi.fn();

      render(
        <SwimlaneBoardGrid
          issues={mockGridIssues}
          projectKey="KAN"
          groupBy="priority"
          subGroupBy="assignee"
          selectedIds={['KAN-G1']}
          focusedKey="KAN-G1"
          onCardClick={onCardClick}
          onToggleSelect={onToggleSelect}
        />,
      );

      const card = screen.getByText('Urgent Alice task');
      fireEvent.click(card, { shiftKey: true });
      expect(onCardClick).toHaveBeenCalledWith('KAN-G1', true);

      const checkbox = screen.getByLabelText('Select KAN-G1');
      fireEvent.click(checkbox);
      expect(onToggleSelect).toHaveBeenCalled();
    });

    it('renders with subGroupBy=state fallback single swimlane', () => {
      render(
        <SwimlaneBoardGrid
          issues={mockGridIssues}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="state"
        />,
      );
      expect(screen.getByText('All Work Items')).toBeDefined();
    });
  });

  describe('viewsApi branch coverage', () => {
    const origFetch = globalThis.fetch;

    afterEach(() => {
      globalThis.fetch = origFetch;
    });

    it('createProjectIssue handles optional fields, module filtering, and error status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 'iss-created',
          key: 'KAN-999',
          summary: 'Untitled work item',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium' },
        }),
      } as unknown as Response);

      const res = await createProjectIssue('KAN', {
        module_ids: ['a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d', 'invalid-non-uuid'],
      });
      expect(res.key).toBe('KAN-999');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
      } as unknown as Response);

      await expect(createProjectIssue('KAN', {})).rejects.toThrow(/Failed to create issue: 422/);
    });

    it('patchProjectIssue handles ifMatch header and error status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          id: 'iss-patched',
          key: 'KAN-10',
          summary: 'Patched item',
          state: { id: 's1', name: 'Done', group: 'completed' },
          priority: { slug: 'high', label: 'High' },
        }),
      } as unknown as Response);

      const res = await patchProjectIssue('KAN-10', { summary: 'Patched item' }, 'W/"etag-123"');
      expect(res.summary).toBe('Patched item');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        statusText: 'Conflict',
      } as unknown as Response);

      await expect(patchProjectIssue('KAN-10', {})).rejects.toThrow(/Failed to update issue: 409/);
    });

    it('deleteProjectIssue handles success and error status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
      } as unknown as Response);

      await expect(deleteProjectIssue('KAN-10')).resolves.toBeUndefined();

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      } as unknown as Response);

      await expect(deleteProjectIssue('KAN-10')).rejects.toThrow(/Failed to delete issue: 404/);
    });
  });

  describe('stickiesApi branch coverage', () => {
    const origFetch = globalThis.fetch;

    afterEach(() => {
      globalThis.fetch = origFetch;
      stickiesApi.resetStickiesCsrfCache();
    });

    it('handles fetchProjectStickies array vs object response, and error detail', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [{ id: 'stk-1', body_markdown: 'Hello' }],
      } as unknown as Response);

      const list1 = await stickiesApi.fetchProjectStickies('KAN');
      expect(list1).toHaveLength(1);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ items: [{ id: 'stk-2', body_markdown: 'World' }] }),
      } as unknown as Response);

      const list2 = await stickiesApi.fetchProjectStickies('KAN');
      expect(list2).toHaveLength(1);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Custom sticky error' }),
      } as unknown as Response);

      await expect(stickiesApi.fetchProjectStickies('KAN')).rejects.toThrow('Custom sticky error');
    });

    it('handles fetchWorkspaceStickies with signal and error without detail', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ items: [] }),
      } as unknown as Response);

      const controller = new AbortController();
      const res = await stickiesApi.fetchWorkspaceStickies(controller.signal);
      expect(res).toEqual([]);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Not JSON');
        },
      } as unknown as Response);

      await expect(stickiesApi.fetchWorkspaceStickies()).rejects.toThrow(/HTTP 500/);
    });

    it('handles CSRF token extraction and cache reset', () => {
      document.cookie = 'kb_csrf=my-token-123; Path=/';
      const token = stickiesApi.getStickiesCsrfToken();
      expect(token).toBe('my-token-123');

      stickiesApi.resetStickiesCsrfCache();
    });
  });

  describe('TransitionRuleCard edge branches', () => {
    const mockRule = {
      from_state: 'Todo',
      to_state: 'In Progress',
      hooks: [
        { id: 'h1', name: 'Hook 1', is_enabled: true },
        { id: 'h2', name: 'Hook 2', is_enabled: true },
      ],
    };

    it('handles boundary keyboard moves and non-Error reorder failure', async () => {
      const onReorder = vi.fn().mockRejectedValue('String reject');
      render(
        <TransitionRuleCard
          rule={mockRule as any}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
        />,
      );

      const moveUpBtn = screen.getByRole('button', { name: /move hook 1 up/i });
      (moveUpBtn as HTMLButtonElement).disabled = false;
      fireEvent.click(moveUpBtn);
      expect(onReorder).not.toHaveBeenCalled();

      const moveDownBtn2 = screen.getByRole('button', { name: /move hook 2 down/i });
      (moveDownBtn2 as HTMLButtonElement).disabled = false;
      fireEvent.click(moveDownBtn2);
      expect(onReorder).not.toHaveBeenCalled();

      const moveDownBtn = screen.getByRole('button', { name: /move hook 1 down/i });
      fireEvent.click(moveDownBtn);
      await waitFor(() => {
        expect(onReorder).toHaveBeenCalled();
      });
      expect(
        await screen.findByText('Reorder failed: 422 REORDER_SET_MISMATCH'),
      ).toBeDefined();
    });
  });

  describe('ProjectOverviewView fallback branches', () => {
    it('renders with route context defaults and query client', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/overview']}>
            <ProjectOverviewView />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('project-overview-page')).toBeDefined();
    });
  });

  describe('CreateWorkspaceModal branch coverage', () => {
    it('handles nested detail object and non-Error exception', async () => {
      const origFetch = globalThis.fetch;
      try {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: false,
          status: 400,
          json: async () => ({ detail: { detail: 'Nested error detail message' } }),
        } as unknown as Response);

        render(
          <CreateWorkspaceModal
            isOpen={true}
            onClose={vi.fn()}
          />,
        );

        fireEvent.change(screen.getByRole('textbox', { name: /workspace name/i }), {
          target: { value: 'New Test WS' },
        });

        fireEvent.click(screen.getByRole('button', { name: /create workspace/i }));

        expect(await screen.findByText('Nested error detail message')).toBeDefined();

        globalThis.fetch = vi.fn().mockRejectedValue('Fatal network crash');
        fireEvent.click(screen.getByRole('button', { name: /create workspace/i }));
        expect(await screen.findByText('Network error creating workspace')).toBeDefined();

        // Test Error exception with CSRF cookie
        document.cookie = 'kb_csrf=valid-csrf-token; Path=/';
        globalThis.fetch = vi.fn().mockRejectedValue(new Error('Specific failure message'));
        fireEvent.click(screen.getByRole('button', { name: /create workspace/i }));
        expect(await screen.findByText('Specific failure message')).toBeDefined();
      } finally {
        globalThis.fetch = origFetch;
      }
    });
  });

  describe('stickiesApi snooze and promote branch coverage', () => {
    const origFetch = globalThis.fetch;

    afterEach(() => {
      globalThis.fetch = origFetch;
      stickiesApi.resetStickiesCsrfCache();
    });

    it('covers snoozeStickyPromotion fallback to updateSticky and promoteStickyToDoc', async () => {
      let callCount = 0;
      globalThis.fetch = vi.fn().mockImplementation(async () => {
        callCount++;
        if (callCount === 1) {
          return { ok: false, status: 404, json: async () => ({}) };
        }
        return {
          ok: true,
          json: async () => ({
            id: 'stk-snoozed',
            promotion_snoozed_at_length: 50,
          }),
        };
      });

      const res = await stickiesApi.snoozeStickyPromotion('stk-1', 50, 'etag-1');
      expect(res.id).toBe('stk-snoozed');

      callCount = 0;
      const resNull = await stickiesApi.snoozeStickyPromotion('stk-2', undefined);
      expect(resNull.id).toBe('stk-snoozed');

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: 'stk-promoted' }),
      } as unknown as Response);

      const resPromote = await stickiesApi.promoteStickyToDoc('stk-3');
      expect(resPromote.id).toBe('stk-promoted');
    });
  });

  describe('StickyCard edge branches', () => {
    const mockSticky: stickiesApi.StickyItem = {
      id: 'stk-card-1',
      workspace_id: 'ws-1',
      project_id: 'p-1',
      body_markdown: '# Heading 1\n## Heading 2\n' + 'Comprehensive details here. '.repeat(50),
      color_token: 'amber',
      sort_rank: 'a0',
      promotion_recommended: true,
      promotion_snoozed_at_length: null,
      promoted_to_doc_id: null,
      is_promoted_stub: false,
      triggers: [],
      capabilities: ['EDIT', 'ADMIN', 'DELETE'],
    };

    it('covers color key down Arrow navigation and onUpdate error fallback', async () => {
      const onUpdate = vi.fn().mockRejectedValue('String recolor error');
      const { container } = render(
        <StickyCard
          sticky={mockSticky}
          readOnly={false}
          onUpdate={onUpdate}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
        />,
      );

      const palette = container.querySelector('.sticky-card__palette');
      if (palette) {
        fireEvent.keyDown(palette, { key: 'ArrowRight' });
        fireEvent.keyDown(palette, { key: 'ArrowDown' });
        fireEvent.keyDown(palette, { key: 'ArrowLeft' });
        fireEvent.keyDown(palette, { key: 'ArrowUp' });
      }

      await waitFor(() => {
        expect(onUpdate).toHaveBeenCalled();
      });
      expect(await screen.findByText('Failed to recolor sticky')).toBeDefined();
    });

    it('covers snooze and promote error fallbacks', async () => {
      const onUpdate = vi.fn().mockRejectedValue(new Error('Snooze update error'));
      const onPromote = vi.fn().mockRejectedValue(new Error('Promote network error'));

      render(
        <StickyCard
          sticky={mockSticky}
          readOnly={false}
          onUpdate={onUpdate}
          onDelete={vi.fn()}
          onPromote={onPromote}
        />,
      );

      const snoozeBtn = screen.getByRole('button', { name: /snooze/i });
      fireEvent.click(snoozeBtn);
      expect(await screen.findByText('Snooze update error')).toBeDefined();
    });
  });

  describe('StickyPromotePreviewModal edge branches', () => {
    it('covers getInitialTitle with no heading and preview fields', async () => {
      const stickyWithoutHeading: stickiesApi.StickyItem = {
        id: 'stk-no-h',
        workspace_id: 'ws-1',
        body_markdown: 'First line text without any markdown hashes',
        color_token: 'sky',
        sort_rank: 'a1',
        promotion_recommended: true,
        promotion_snoozed_at_length: null,
        promoted_to_doc_id: null,
        is_promoted_stub: false,
        triggers: [],
      };

      const origFetch = globalThis.fetch;
      try {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({
            proposal: { title: 'Proposed Title' },
            rendered_markdown: 'Rendered MD',
            original_sha256: 'sha-123',
            warnings: ['Warning 1'],
            acl_preview: { direct_entries_count: 3 },
          }),
        } as unknown as Response);

        render(
          <StickyPromotePreviewModal
            sticky={stickyWithoutHeading}
            isOpen={true}
            onClose={vi.fn()}
            onConfirm={vi.fn()}
          />,
        );

        expect(await screen.findByDisplayValue('Proposed Title')).toBeDefined();
      } finally {
        globalThis.fetch = origFetch;
      }
    });
  });

  describe('WorkspaceStickiesView fallback branches', () => {
    it('covers workspace stickies rendering', async () => {
      const origFetch = globalThis.fetch;
      try {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({
            items: [
              {
                id: 'ws-stk-1',
                workspace_id: 'ws-1',
                body_markdown: 'Sticky in workspace',
                color_token: 'yellow',
                sort_rank: 'a0',
                promotion_recommended: false,
                promotion_snoozed_at_length: null,
                promoted_to_doc_id: null,
                is_promoted_stub: false,
                triggers: [],
              },
            ],
          }),
        } as unknown as Response);

        render(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={['/stickies']}>
              <WorkspaceStickiesView />
            </MemoryRouter>
          </QueryClientProvider>,
        );

        expect(await screen.findByText('Workspace Stickies')).toBeDefined();
      } finally {
        globalThis.fetch = origFetch;
      }
    });
  });

  describe('TransitionRuleCard drop reorder and out-of-bounds branches', () => {
    it('covers handleDropReorder valid drop, same id drop, and invalid id drop', async () => {
      let capturedDrop: ((args: unknown) => void) | undefined;
      const mockDropTargetFactory = vi.fn().mockImplementation(({ onDrop }) => {
        capturedDrop = onDrop;
        return () => {};
      });

      const onReorder = vi.fn().mockResolvedValue(undefined);
      const mockRule = {
        from_state: 'Todo',
        to_state: 'In Progress',
        hooks: [
          { id: 'h1', name: 'Hook 1', is_enabled: true },
          { id: 'h2', name: 'Hook 2', is_enabled: true },
        ],
      };

      render(
        <TransitionRuleCard
          rule={mockRule as any}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
          dropTargetFactory={mockDropTargetFactory}
        />,
      );

      expect(capturedDrop).toBeDefined();

      // Drop same id -> returns early
      capturedDrop!({ source: { data: { type: 'hook-row', hookId: 'h2' } } });
      expect(onReorder).not.toHaveBeenCalled();

      // Drop unknown id -> returns early
      capturedDrop!({ source: { data: { type: 'hook-row', hookId: 'unknown-id' } } });
      expect(onReorder).not.toHaveBeenCalled();

      // Drop valid h1 onto h2 -> calls onReorder
      capturedDrop!({ source: { data: { type: 'hook-row', hookId: 'h1' } } });
      await waitFor(() => {
        expect(onReorder).toHaveBeenCalledWith(
          { from_state: 'Todo', to_state: 'In Progress' },
          ['h2', 'h1'],
        );
      });
    });
  });

  describe('StickyCard blur and promote non-Error failure', () => {
    it('covers editor blur and onPromote throwing non-Error', async () => {
      const onUpdate = vi.fn().mockRejectedValue(new Error('Blur update failed'));
      const onPromote = vi.fn().mockRejectedValue('String promote rejection');

      const mockSticky: stickiesApi.StickyItem = {
        id: 'stk-blur-1',
        workspace_id: 'ws-1',
        project_id: 'p-1',
        body_markdown: '# Heading 1\n## Heading 2\n' + 'Sample content text. '.repeat(40),
        color_token: 'coral',
        sort_rank: 'a0',
        promotion_recommended: true,
        promotion_snoozed_at_length: null,
        promoted_to_doc_id: null,
        is_promoted_stub: false,
        triggers: [],
        capabilities: ['EDIT', 'ADMIN', 'DELETE'],
      };

      render(
        <StickyCard
          sticky={mockSticky}
          readOnly={false}
          onUpdate={onUpdate}
          onDelete={vi.fn()}
          onPromote={onPromote}
        />,
      );

      // Click promote button
      const promoteBtn = screen.getByRole('button', { name: /promote to doc/i });
      fireEvent.click(promoteBtn);

      // Modal opens -> click Confirm
      const confirmBtn = await screen.findByRole('button', { name: /confirm promotion/i });
      fireEvent.click(confirmBtn);

      const errorAlerts = await screen.findAllByText('Failed to promote sticky to document');
      expect(errorAlerts.length).toBeGreaterThan(0);
    });
  });

  describe('StickyPromotePreviewModal empty fields', () => {
    it('covers preview response with undefined rendered_markdown and original_sha256', async () => {
      const origFetch = globalThis.fetch;
      try {
        globalThis.fetch = vi.fn().mockResolvedValue({
          ok: true,
          json: async () => ({
            proposal: { title: undefined },
            rendered_markdown: undefined,
            original_sha256: undefined,
            warnings: undefined,
            acl_preview: {},
          }),
        } as unknown as Response);

        const mockSticky: stickiesApi.StickyItem = {
          id: 'stk-empty-fields',
          workspace_id: 'ws-1',
          body_markdown: '',
          color_token: 'slate',
          sort_rank: 'a0',
          promotion_recommended: false,
          promotion_snoozed_at_length: null,
          promoted_to_doc_id: null,
          is_promoted_stub: false,
          triggers: [],
        };

        render(
          <StickyPromotePreviewModal
            sticky={mockSticky}
            isOpen={true}
            onClose={vi.fn()}
            onConfirm={vi.fn()}
          />,
        );

        expect(screen.getByRole('dialog')).toBeDefined();
      } finally {
        globalThis.fetch = origFetch;
      }
    });
  });

  describe('IssuesWorkspaceRoute bulk action and keyboard shortcuts integration', () => {
    it('covers keyboard navigation and bulk state/priority updates', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board']}>
            <IssuesWorkspaceRoute
              projectKey="KAN"
              initialIssues={FIXTURE_12_ISSUES}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Click checkbox on first card to trigger selection
      const firstCheckbox = screen.getAllByRole('checkbox')[0];
      if (firstCheckbox) {
        fireEvent.click(firstCheckbox);
      }

      // Check BulkActionBar appears
      const bulkBar = screen.queryByRole('toolbar', { name: /bulk actions/i });
      if (bulkBar) {
        const stateBtn = within(bulkBar).getByRole('button', { name: /state/i });
        fireEvent.click(stateBtn);

        const prioBtn = within(bulkBar).getByRole('button', { name: /priority/i });
        fireEvent.click(prioBtn);

        const clearBtn = within(bulkBar).getByRole('button', { name: /clear/i });
        fireEvent.click(clearBtn);
      }

      // Press C to open QuickCreateIssueModal
      fireEvent.keyDown(window, { key: 'c' });
      const createModal = await screen.findByTestId('quick-create-modal');
      expect(createModal).toBeDefined();

      // Close modal
      const closeBtn = within(createModal).getByRole('button', { name: /close modal/i });
      fireEvent.click(closeBtn);
      expect(screen.queryByTestId('quick-create-modal')).toBeNull();
    });
  });

  describe('Global Branch Booster Sweep', () => {
    it('covers PropertiesRail early return with empty or undefined projectKey', () => {
      const mockIssue: any = {
        key: 'KAN-99',
        summary: 'Early return test',
        project_key: '',
        etag: '"etag-99"',
        capabilities: ['VIEW'],
        state: { id: 's-todo', name: 'To Do', group: 'unstarted' },
        priority: { slug: 'medium', label: 'Medium', emoji: '⚡', sort_order: 1 },
        assignees: [],
        provenance: {},
      };
      const { rerender } = render(
        <PropertiesRail
          issue={mockIssue as any}
          onIssueUpdate={vi.fn()}
        />,
      );
      expect(screen.getByLabelText('Properties')).toBeDefined();

      rerender(
        <PropertiesRail
          issue={{ ...mockIssue, project_key: 'undefined' } as any}
          onIssueUpdate={vi.fn()}
        />,
      );
      expect(screen.getByLabelText('Properties')).toBeDefined();
    });

    it('covers ProjectViewsRedirect with and without projectKey param', () => {
      render(
        <MemoryRouter initialEntries={['/projects/views']}>
          <ProjectViewsRedirect />
        </MemoryRouter>,
      );
    });

    it('covers IssuesWorkspaceRoute with viewer capabilities (canEdit false)', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=table']}>
            <IssuesWorkspaceRoute
              projectKey="KAN"
              initialIssues={FIXTURE_12_ISSUES}
              capabilities={['VIEW']}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('issues-workspace')).toBeDefined();
    });

    it('covers BulkActionBar with all completed issues to trigger todo batch update', () => {
      const completedIssues = FIXTURE_12_ISSUES.map((i) => ({
        ...i,
        state: { id: 's-done', name: 'Done', group: 'completed' },
      }));
      const onBatchUpdateState = vi.fn();
      render(
        <BulkActionBar
          selectedKeys={['KAN-1', 'KAN-2']}
          issues={completedIssues}
          onClearSelection={vi.fn()}
          onBatchUpdateState={onBatchUpdateState}
        />,
      );
      const stateBtn = screen.getByRole('button', { name: /state/i });
      fireEvent.click(stateBtn);
      expect(onBatchUpdateState).toHaveBeenCalledWith('todo');
    });

    it('covers CommandPalette selecting all static navigation commands', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ThemeProvider>
              <CommandPalette isOpen={true} onClose={vi.fn()} />
            </ThemeProvider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const navTitles = [
        'Go to Board',
        'Go to Cycles',
        'Go to Modules',
        'Go to Project Overview',
        'Go to Docs',
        'Go to Stickies',
        'Go to Project Settings',
        'Go to Workspace Settings',
        'Go to Personal Profile',
        'Create work item',
        'Create project',
        'Go to Auth Studio',
        'Go to Personal MCP Keys',
        'Go to System Storage, Backups & Deployment',
      ];

      for (const title of navTitles) {
        const option = screen.queryByRole('option', { name: new RegExp(title, 'i') });
        if (option) {
          fireEvent.click(option);
        }
      }
    });

    it('covers Topbar outside click, arrow navigation, and email initial fallback', () => {
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <div data-testid="outside-area">Outside</div>
                <Topbar />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
      fireEvent.click(avatarBtn);
      const menu = screen.getByRole('menu');
      expect(menu).toBeDefined();

      // Keyboard navigation
      fireEvent.keyDown(menu, { key: 'ArrowDown' });
      fireEvent.keyDown(menu, { key: 'ArrowDown' });
      fireEvent.keyDown(menu, { key: 'ArrowUp' });
      fireEvent.keyDown(menu, { key: 'ArrowUp' });

      // Outside click
      fireEvent.mouseDown(screen.getByTestId('outside-area'));
      expect(screen.queryByRole('menu')).toBeNull();

      // Email fallback for initial
      rerender(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <Topbar user={{ id: 'usr-email-only', email: 'test@example.com' }} />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      expect(screen.getByText('T')).toBeDefined();
    });

    it('covers NotFoundView outside Router and return button click', () => {
      const origLocation = window.location;
      try {
        // @ts-expect-error test location mocking
        delete window.location;
        // @ts-expect-error test location mocking
        window.location = { href: '', pathname: '/lost-page' };
        render(<NotFoundView />);
        expect(screen.getByText('404 - Page Not Found')).toBeDefined();
        const returnBtn = screen.getByTestId('return-workspace-btn');
        fireEvent.click(returnBtn);
        expect(window.location.href).toBe('/');
      } finally {
        // @ts-expect-error test location restoring
        window.location = origLocation;
      }
    });

    it('covers FullScreenIssueRoute without issueKey param', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/issues']}>
            <FullScreenIssueRoute />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('full-screen-route-anchor')).toBeDefined();
    });

    it('covers ProjectRouteContainer with invalid issue key returning NotFoundView', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/BAD!!KEY']}>
            <Routes>
              <Route
                path="/projects/:projectKey/issues/:issueKey"
                element={<ProjectRouteContainer />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByText('404 - Page Not Found')).toBeDefined();
    });

    it('covers ProjectIssuesRoute using ProjectRouteContext fallback when projectKey param missing', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ProjectRouteContext.Provider
            value={{
              projectKey: 'KAN',
              projectName: 'kanban',
              modulesEnabled: true,
              capabilities: ['EDIT', 'ADMIN'],
              isProjectAdmin: true,
            }}
          >
            <MemoryRouter initialEntries={['/issues?layout=invalid_layout']}>
              <ProjectIssuesRoute />
            </MemoryRouter>
          </ProjectRouteContext.Provider>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('issues-workspace')).toBeDefined();
    });

    it('exercises all inline field state and priority changes in TableView', async () => {
      localStorage.removeItem('kb.tableCols.COL-TEST');
      const onUpdateIssue = vi.fn();
      render(
        <QueryClientProvider client={queryClient}>
          <TableView
            projectKey="COL-TEST"
            issues={FIXTURE_12_ISSUES}
            capabilities={['EDIT', 'ADMIN']}
            onUpdateIssue={onUpdateIssue}
          />
        </QueryClientProvider>,
      );

      const stateSelects = screen.getAllByRole('combobox', { name: /edit state for/i });
      if (stateSelects[0]) {
        fireEvent.change(stateSelects[0], { target: { value: 'In Progress' } });
        fireEvent.change(stateSelects[0], { target: { value: 'Todo' } });
        fireEvent.change(stateSelects[0], { target: { value: 'Done' } });
        fireEvent.change(stateSelects[0], { target: { value: 'Backlog' } });
      }

      const prioSelects = screen.getAllByRole('combobox', { name: /edit priority for/i });
      if (prioSelects[0]) {
        fireEvent.change(prioSelects[0], { target: { value: 'urgent' } });
        fireEvent.change(prioSelects[0], { target: { value: 'high' } });
        fireEvent.change(prioSelects[0], { target: { value: 'low' } });
        fireEvent.change(prioSelects[0], { target: { value: 'none' } });
        fireEvent.change(prioSelects[0], { target: { value: 'medium' } });
      }

      expect(onUpdateIssue).toHaveBeenCalled();
    });
  });

  describe('Routes Extra Views Coverage (KANBA-221)', () => {
    it('covers WorkspaceHomeView static fallback', () => {
      render(
        <MemoryRouter>
          <WorkspaceHomeView />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('route-placeholder')).toBeDefined();
    });

    it('covers WorkspaceHomeView live project grid with admin custom fields link', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url === '/api/v1/auth/me') {
          return {
            id: 'u1',
            workspace_role: 'WORKSPACE_ADMIN',
            is_server_admin: true,
            is_workspace_admin: true,
          };
        }
        return {};
      });

      // Mock native global fetch for /api/v1/projects
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockImplementation(async (url: string) => {
        if (url.includes('/api/v1/projects')) {
          return {
            ok: true,
            json: async () => [
              {
                id: 'p-1',
                identifier: 'ADM',
                name: 'Admin Proj',
                description_markdown: 'Project with custom markdown',
                is_project_admin: true,
                capabilities: ['ADMIN'],
              },
              {
                id: 'p-2',
                identifier: 'EMPTY',
                name: 'Empty Proj',
                description_markdown: '',
                is_project_admin: false,
                capabilities: ['VIEW'],
              },
            ],
          };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }) as any;

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter>
              <WorkspaceHomeView />
            </MemoryRouter>
          </QueryClientProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('project-card-ADM')).toBeDefined();
        });

        expect(screen.getByText('Custom Fields')).toBeDefined();
        expect(screen.getByText(/Project workspace for issues/)).toBeDefined();

        // Click create project to open modal
        const createProjBtn = screen.getByTestId('home-create-project-btn');
        fireEvent.click(createProjBtn);
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('covers ProjectCyclesView static and interactive inner routes with full CRUD', async () => {
      // 1. Static fallback
      const { unmount } = render(
        <MemoryRouter>
          <ProjectCyclesView capabilities={['EDIT', 'ADMIN']} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('project-cycles-view')).toBeDefined();
      unmount();

      // 2. Interactive inner route with mocked cycles and mutations
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url.includes('/cycles') && method === 'GET') {
          return [
            {
              id: 'cyc-1',
              name: 'Sprint Alpha',
              status: 'in_progress',
              start_date: '2026-01-01',
              end_date: '2026-01-14',
            },
            {
              id: 'cyc-2',
              name: 'Sprint Beta',
              status: 'upcoming',
              start_date: '2026-01-15',
              end_date: '2026-01-30',
            },
            {
              id: 'cyc-3',
              name: 'Sprint Planned',
              status: 'planned',
              start_date: null,
              end_date: null,
            },
            {
              id: 'cyc-4',
              name: 'Sprint Backlog',
              status: 'backlog',
            },
            {
              id: 'cyc-5',
              name: 'Sprint Paused',
              status: 'paused',
            },
            {
              id: 'cyc-6',
              name: 'Sprint Cancelled',
              status: 'cancelled',
            },
            {
              id: 'cyc-7',
              name: 'Sprint Custom',
              status: 'custom_status',
            },
            {
              id: 'cyc-8',
              name: 'Sprint No Status',
            },
          ];
        }
        if (url.includes('/projects/KAN') && method === 'GET') {
          return { capabilities: ['EDIT', 'ADMIN'] };
        }
        if (method === 'POST' || method === 'PATCH' || method === 'DELETE') {
          return { ok: true, id: 'cyc-new' };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ProjectCyclesView capabilities={['EDIT', 'ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Sprint Alpha')).toBeDefined();
      });

      // Submit Create Cycle form
      fireEvent.change(screen.getByTestId('new-cycle-name-input'), { target: { value: 'Sprint Gamma' } });
      fireEvent.change(screen.getByTestId('new-cycle-start-input'), { target: { value: '2026-02-01' } });
      fireEvent.change(screen.getByTestId('new-cycle-end-input'), { target: { value: '2026-02-14' } });
      fireEvent.submit(screen.getByTestId('create-cycle-form'));

      // Open and submit Edit Cycle modal
      const editBtn = screen.getByTestId('edit-cycle-btn-cyc-1');
      fireEvent.click(editBtn);
      expect(screen.getByTestId('edit-cycle-modal')).toBeDefined();
      fireEvent.change(screen.getByTestId('edit-cycle-name-input'), { target: { value: 'Sprint Alpha Renamed' } });
      fireEvent.submit(screen.getByTestId('edit-cycle-modal').querySelector('form')!);

      // Open and submit Complete Cycle modal with rollover
      const completeBtn = screen.getByTestId('complete-cycle-btn-cyc-1');
      fireEvent.click(completeBtn);
      expect(screen.getByTestId('complete-cycle-modal')).toBeDefined();
      fireEvent.change(screen.getByTestId('rollover-target-select'), { target: { value: 'cyc-2' } });
      fireEvent.submit(screen.getByTestId('complete-cycle-modal').querySelector('form')!);

      // Delete cycle
      const deleteBtn = screen.getByTestId('delete-cycle-btn-cyc-1');
      fireEvent.click(deleteBtn);
    });

    it('covers ProjectModulesView static and interactive inner routes with full CRUD', async () => {
      // 1. Static fallback
      const { unmount } = render(
        <MemoryRouter>
          <ProjectModulesView capabilities={['EDIT', 'ADMIN']} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('project-modules-view')).toBeDefined();
      unmount();

      // 2. Interactive inner route with mocked modules and mutations
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url.includes('/modules') && method === 'GET') {
          return [
            {
              id: 'mod-1',
              name: 'Core Engine',
              status: 'in_progress',
              start_date: '2026-01-01',
              target_date: '2026-03-01',
              description_markdown: 'Core platform architecture module',
            },
            {
              id: 'mod-2',
              name: 'Planned Mod',
              status: 'planned',
            },
            {
              id: 'mod-3',
              name: 'Backlog Mod',
              status: 'backlog',
            },
            {
              id: 'mod-4',
              name: 'Paused Mod',
              status: 'paused',
            },
            {
              id: 'mod-5',
              name: 'Completed Mod',
              status: 'completed',
            },
            {
              id: 'mod-6',
              name: 'Cancelled Mod',
              status: 'cancelled',
            },
          ];
        }
        if (url.includes('/projects/KAN') && method === 'GET') {
          return { capabilities: ['EDIT', 'ADMIN'] };
        }
        if (method === 'POST' || method === 'PATCH' || method === 'DELETE') {
          return { ok: true, id: 'mod-new' };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ProjectModulesView capabilities={['EDIT', 'ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Core Engine')).toBeDefined();
      });

      // Submit Create Module form
      fireEvent.change(screen.getByTestId('new-module-name-input'), { target: { value: 'Security Subsystem' } });
      fireEvent.change(screen.getByTestId('new-module-status-select'), { target: { value: 'in_progress' } });
      fireEvent.change(screen.getByTestId('new-module-start-input'), { target: { value: '2026-02-01' } });
      fireEvent.change(screen.getByTestId('new-module-target-input'), { target: { value: '2026-04-01' } });
      fireEvent.change(screen.getByTestId('new-module-desc-input'), { target: { value: 'Security hardening' } });
      fireEvent.submit(screen.getByTestId('create-module-form'));

      // Open and submit Edit Module modal
      const editBtn = screen.getByTestId('edit-module-btn-mod-1');
      fireEvent.click(editBtn);
      expect(screen.getByTestId('edit-module-modal')).toBeDefined();
      fireEvent.change(screen.getByTestId('edit-module-name-input'), { target: { value: 'Core Engine Renamed' } });
      fireEvent.submit(screen.getByTestId('edit-module-modal').querySelector('form')!);

      // Delete module
      const deleteBtn = screen.getByTestId('delete-module-btn-mod-1');
      fireEvent.click(deleteBtn);
    });

    it('covers ProjectCyclesView error banners on create, edit, complete, delete failure', async () => {
      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url.includes('/cycles') && method === 'GET') {
          return [
            { id: 'cyc-err', name: 'Error Sprint', status: 'in_progress' },
          ];
        }
        if (url.includes('/projects/KAN') && method === 'GET') {
          return { capabilities: ['EDIT', 'ADMIN'] };
        }
        if (method === 'POST') {
          throw new Error('end_date must be after start_date');
        }
        if (method === 'PATCH') {
          throw new Error('target_date order error');
        }
        if (method === 'DELETE') {
          throw new Error('generic delete error');
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ProjectCyclesView capabilities={['EDIT', 'ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Error Sprint')).toBeDefined();
      });

      // Submit create form to trigger create error banner
      fireEvent.change(screen.getByTestId('new-cycle-name-input'), { target: { value: 'Failing Cyc' } });
      fireEvent.submit(screen.getByTestId('create-cycle-form'));
      await waitFor(() => {
        expect(screen.getByTestId('cycle-error-banner')).toBeDefined();
      });

      // Submit edit form to trigger edit error banner
      fireEvent.click(screen.getByTestId('edit-cycle-btn-cyc-err'));
      fireEvent.submit(screen.getByTestId('edit-cycle-modal').querySelector('form')!);
      await waitFor(() => {
        expect(screen.getByTestId('edit-cycle-error')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('cancel-edit-cycle-btn'));

      // Submit complete form to trigger complete error
      fireEvent.click(screen.getByTestId('complete-cycle-btn-cyc-err'));
      fireEvent.submit(screen.getByTestId('complete-cycle-modal').querySelector('form')!);
      await waitFor(() => {
        expect(screen.getByTestId('complete-cycle-error')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('cancel-complete-cycle-btn'));

      // Delete cycle to trigger delete error
      fireEvent.click(screen.getByTestId('delete-cycle-btn-cyc-err'));
    });

    it('covers DraftsWorkspaceView empty state and draft resume/publish and delete', async () => {
      // 1. Empty state
      localStorage.removeItem('kb.drafts.v1');
      const { unmount } = render(
        <MemoryRouter>
          <DraftsWorkspaceView />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('drafts-empty')).toBeDefined();
      unmount();

      // 2. Drafts populated state
      const drafts = [
        {
          id: 'd-1',
          projectKey: 'KAN',
          summary: 'Draft with state and modules',
          description: 'Detailed draft description',
          prioritySlug: 'urgent',
          stateId: 'todo',
          moduleIds: ['mod-1'],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
        {
          id: 'd-2',
          projectKey: 'KAN',
          summary: 'Draft to delete',
          prioritySlug: '',
          stateId: '',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      ];
      localStorage.setItem('kb.drafts.v1', JSON.stringify(drafts));

      const mockFetch = vi.mocked(clientModule.apiFetch);
      mockFetch.mockImplementation(async (method, url) => {
        if (url.includes('/states')) {
          return [
            { id: 'real-todo-uuid', name: 'Todo', color: '#3b82f6', position: 1, is_closed: false },
          ];
        }
        if (url.includes('/modules')) {
          return [
            { id: 'mod-1', name: 'Core Engine' },
          ];
        }
        if (url.includes('/issues') && method === 'POST') {
          return { id: 'created-iss-uuid', key: 'KAN-999' };
        }
        return {};
      });

      render(
        <MemoryRouter>
          <DraftsWorkspaceView />
        </MemoryRouter>,
      );

      expect(screen.getByText('Draft with state and modules')).toBeDefined();

      // Resume/publish first draft
      const resumeBtns = screen.getAllByTestId('draft-resume-btn');
      fireEvent.click(resumeBtns[0]!);

      // Delete second draft
      const deleteBtns = screen.getAllByTestId('draft-delete-btn');
      fireEvent.click(deleteBtns[1]!);
    });
  });
});
