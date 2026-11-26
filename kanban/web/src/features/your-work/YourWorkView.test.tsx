import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { YourWorkView } from './YourWorkView';
import { apiFetch } from '../../api/client';
import { ShellPanelsProvider, registerShellPanel } from '../../app/shellPanels';

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

  it('dispatches kb:open-issue-peek when clicking the issue key anchor directly', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('peek-link-KAN-101')).toBeDefined();
    });
    const peekListener = vi.fn();
    window.addEventListener('kb:open-issue-peek', peekListener);
    fireEvent.click(screen.getByTestId('peek-link-KAN-101'));
    expect(peekListener).toHaveBeenCalled();
    window.removeEventListener('kb:open-issue-peek', peekListener);
  });

  it('allows switching back to Assigned to Me tab from Created by Me', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('tab-created-by-me')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('tab-created-by-me'));
    expect(screen.getByTestId('tab-created-by-me').getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByTestId('tab-assigned-to-me'));
    expect(screen.getByTestId('tab-assigned-to-me').getAttribute('aria-selected')).toBe('true');
  });

  it('filters active tab items using project key query', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('KAN-101')).toBeDefined();
    });
    const searchInput = screen.getByLabelText('Filter your work items');
    fireEvent.change(searchInput, { target: { value: 'ops' } });
    expect(screen.queryByText('KAN-101')).toBeNull();
    expect(screen.getByText('OPS-201')).toBeDefined();
  });

  it('renders fallback when QueryClientContext is not provided', () => {
    render(<YourWorkView />);
    expect(screen.getByTestId('your-work-view')).toBeDefined();
    expect(screen.getByText('No work items found')).toBeDefined();
  });

  it('handles null user identity and projects object format', async () => {
    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      const p = path as string;
      if (p === '/api/v1/auth/me') return null;
      if (p === '/api/v1/projects') return { items: [{ id: 'proj-1', identifier: 'KAN', name: 'Kanban Project' }] };
      if (p.includes('/notifications')) return { items: [] };
      return [];
    });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('your-work-view')).toBeDefined();
    });
    expect(screen.getByTestId('badge-assigned-count').textContent).toBe('0');
  });

  it('covers all assignment, creation, subscription and rendering branches', async () => {
    const variedIssues: unknown[] = [
      {
        id: 'iss-email',
        key: 'KAN-110',
        summary: 'Email match issue',
        project_key: 'KAN',
        created_by: 'user-123',
        state: { id: 's-1', name: 'In Progress', slug: 'in_progress', group: 'in_progress', color: '#2563eb' },
        priority: { id: 'p-urgent', slug: 'urgent' }, // no label -> uses slug
        assignees: [
          { id: 'diff-id', principal: { email: 'alice@example.com' } },
        ],
        subscribed: false,
      },
      {
        id: 'iss-handle-at',
        key: 'KAN-111',
        summary: 'Handle with at prefix',
        created_by_handle: '@alice',
        state: undefined, // no state
        priority: { id: 'p-low', slug: 'low', label: 'Low' },
        assignees: [
          { id: 'diff-id-2', principal: { handle: '@alice' } },
        ],
        subscribed: false,
      },
      {
        id: 'iss-no-dash',
        key: 'GLOBALKEY',
        summary: 'Key without dash and medium priority',
        created_by_id: 'user-999',
        priority: { id: 'p-med', slug: 'medium', label: 'Medium' },
        assignees: [],
        subscribed: true,
      },
      {
        id: 'iss-no-prio',
        key: 'KAN-112',
        summary: 'Issue without priority',
        project_key: 'KAN',
        created_by_id: 'user-999',
        state: { id: 's-2', name: 'Todo', slug: 'todo', group: 'todo', color: '#64748b' },
        priority: null,
        assignees: [],
        subscribed: false,
      },
    ];

    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      const p = path as string;
      if (p === '/api/v1/auth/me') return mockUser;
      if (p === '/api/v1/projects') return [{ id: 'p-1', key: 'KAN', name: 'Kanban' }, { id: 'p-fail', key: 'FAIL', name: 'Failing' }];
      if (p.includes('/projects/FAIL/issues')) throw new Error('API failure');
      if (p.includes('/projects/KAN/issues')) return { items: variedIssues };
      if (p.includes('/notifications')) {
        return {
          items: [
            { id: 'n-1', link: '/issues?peek=KAN-112' },
            { id: 'n-2', link: '/other/path' },
            { id: 'n-3' },
          ],
        };
      }
      return [];
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('KAN-110')).toBeDefined();
    });

    expect(screen.getByText('Email match issue')).toBeDefined();
    expect(screen.getByText('urgent')).toBeDefined();

    // Switch to Created by Me tab
    fireEvent.click(screen.getByTestId('tab-created-by-me'));
    await waitFor(() => {
      expect(screen.getByText('KAN-111')).toBeDefined();
    });

    // Switch to Subscribed tab (which has GLOBALKEY and KAN-112 from notification link peek)
    fireEvent.click(screen.getByTestId('tab-subscribed'));
    await waitFor(() => {
      expect(screen.getByText('GLOBALKEY')).toBeDefined();
      expect(screen.getByText('KAN-112')).toBeDefined();
    });

    // Filter by issue key
    const searchInput = screen.getByLabelText('Filter your work items');
    fireEvent.change(searchInput, { target: { value: 'globalkey' } });
    expect(screen.getByText('GLOBALKEY')).toBeDefined();
    expect(screen.queryByText('KAN-112')).toBeNull();
  });

  it('covers edge branches for missing project_key, undefined assignees, empty items object, and user without handle', async () => {
    mockApiFetch.mockImplementation(async (method, path) => {
      await Promise.resolve();
      const p = path as string;
      if (p === '/api/v1/auth/me') return { id: 'u-1', email: 'test@example.com' }; // no handle
      if (p === '/api/v1/projects') return [{ id: 'p-1', key: 'TEST', name: 'Test' }, { id: 'p-2', key: 'EMPTY', name: 'Empty' }];
      if (p.includes('/projects/EMPTY/issues')) return {}; // data.items is undefined
      if (p.includes('/projects/TEST/issues')) {
        return [
          {
            id: 'iss-no-pk',
            key: 'TEST-123', // has dash, no project_key property
            summary: 'No project key test',
            created_by_id: 'u-1',
            assignees: undefined, // covers issue.assignees ?? [] fallback
          },
        ];
      }
      if (p.includes('/notifications')) return { items: [] };
      return [];
    });

    renderComponent();

    // Switch to Created by Me tab
    await waitFor(() => {
      expect(screen.getByTestId('tab-created-by-me')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('tab-created-by-me'));

    await waitFor(() => {
      expect(screen.getByText('TEST-123')).toBeDefined();
    });
    expect(screen.getByText('No project key test')).toBeDefined();
  });

  describe('StudioDocLink Header Integration and Shift-Left Invariants (KAN-470)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders your-work-doc-link with correct href, label, and title in header row in Light and Dark themes', async () => {
      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = renderComponent();

        await waitFor(() => {
          expect(screen.getByTestId('your-work-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('your-work-doc-link');
        expect(docLink.getAttribute('href')).toBe('/docs/user-tasks-and-qa-matrix');
        expect(docLink.getAttribute('aria-label')).toBe('Your Work Guide ->');
        expect(docLink.textContent).toContain('Your Work Guide ->');

        const titleRow = docLink.closest('.your-work-title-row');
        expect(titleRow).not.toBeNull();
        expect(titleRow?.querySelector('.your-work-title')?.textContent).toBe('Your work');

        const headerText = docLink.closest('.your-work-header-text');
        expect(headerText).not.toBeNull();

        unmount();
      }
    });

    it('supports keyboard focus navigation on your-work-doc-link', async () => {
      renderComponent();

      await waitFor(() => {
        expect(screen.getByTestId('your-work-doc-link')).toBeDefined();
      });

      const docLink = screen.getByTestId('your-work-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
    });

    it('activates in-app help panel via ShellPanelsProvider when doc link is clicked', async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });

      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string; title?: string } | undefined)?.title} at {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <QueryClientProvider client={queryClient}>
              <MemoryRouter initialEntries={['/your-work']}>
                <YourWorkView />
              </MemoryRouter>
            </QueryClientProvider>
          </ShellPanelsProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('your-work-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('your-work-doc-link');
        fireEvent.click(docLink);

        await waitFor(() => {
          expect(screen.getByTestId('in-app-help-panel')).toBeDefined();
        });

        const helpPanel = screen.getByTestId('in-app-help-panel');
        expect(helpPanel.textContent).toContain('Your Work Guide ->');
        expect(helpPanel.textContent).toContain('/docs/user-tasks-and-qa-matrix');
      } finally {
        unregister();
      }
    });

    it('verifies YourWorkView.tsx contains zero inline style attributes (KAN-470 CSP invariant)', () => {
      const tsxPath = path.resolve(__dirname, 'YourWorkView.tsx');
      const content = fs.readFileSync(tsxPath, 'utf8');

      // Reject any style={{...}} prop in TSX
      const inlineStyleMatch = /style=\{\{/.exec(content);
      expect(inlineStyleMatch).toBeNull();
    });

    it('verifies HTML 4.10.4 compliance (zero interactive elements nested in label tags)', () => {
      const tsxPath = path.resolve(__dirname, 'YourWorkView.tsx');
      const content = fs.readFileSync(tsxPath, 'utf8');

      // Zero FieldHelpHint or button nested in label
      expect(content).not.toMatch(/<label[^>]*>[^<]*<button/);
      expect(content).not.toMatch(/<label[^>]*>[^<]*<FieldHelpHint/);
    });

    it('verifies YourWorkView.css enforces canonical tokens, 44px tap targets, and clean wrapping on mobile', () => {
      const cssPath = path.resolve(__dirname, 'YourWorkView.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      expect(cssContent).toContain('.your-work-title-row');
      expect(cssContent).toContain('flex-wrap: wrap');

      expect(cssContent).toContain('@media (max-width: 767px)');
      expect(cssContent).toContain('min-height: var(--tap-min, 44px)');
      expect(cssContent).toContain('.your-work-header-text .kb-studio-doc-link');
    });
  });
});
