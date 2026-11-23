// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssueSurfaceRoot } from '../../features/drawer/IssueSurface';
import { IssueHeader } from '../../features/drawer/IssueHeader';
import { IssueSurfaceSlotsContext, type IssueDetail } from '../../features/drawer/slots';
import { LinkGraphAction } from '../../features/drawer-actions/LinkGraphAction';
import { IssueOverflowMenu } from '../../features/drawer-actions/IssueOverflowMenu';
import { apiClient } from '../../api/client';
import * as railApi from '../../features/drawer-rail/railApi';
import * as actionsApi from '../../features/drawer-actions/actionsApi';
import type { IssueItem } from '../../features/views/viewsApi';

const mockIssue: IssueDetail = {
  id: '01931234-5678-7000-8000-000000000100',
  key: 'KAN-100',
  object_id: '01931234-5678-7000-8000-000000000100',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Issue Actions Parity and Disambiguation',
  description_markdown: 'Ensure split-pane toolbar parity and deduplicate adjacent link icons.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: '8h',
  },
  state: {
    id: 'state-todo',
    name: 'Todo',
    group: 'unstarted',
  },
  capabilities: ['VIEW', 'EDIT', 'TRANSITION', 'COMMENT', 'ADMIN', 'DELETE'],
  etag: '"etag-kan-100"',
};

const mockIssuesList: IssueItem[] = [
  {
    id: '01931234-5678-7000-8000-000000000099',
    key: 'KAN-99',
    summary: 'Previous Work Item',
    state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
    priority: { slug: 'medium', label: 'Medium' },
  },
  {
    id: '01931234-5678-7000-8000-000000000100',
    key: 'KAN-100',
    summary: 'Issue Actions Parity and Disambiguation',
    state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
    priority: { slug: 'high', label: 'High' },
  },
  {
    id: '01931234-5678-7000-8000-000000000101',
    key: 'KAN-101',
    summary: 'Next Work Item',
    state: { id: 'state-done', name: 'Done', group: 'completed' },
    priority: { slug: 'low', label: 'Low' },
  },
];

describe('MenuConsolidation KAN-366 Feature Unit Tests', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
    localStorage.clear();

    vi.spyOn(apiClient, 'get').mockImplementation((url: string) => {
      if (url.includes('/api/v1/auth/me')) {
        return Promise.resolve({
          id: 'u-admin',
          principal_id: 'u-admin',
          handle: 'admin',
          display_name: 'Administrator',
        });
      }
      return Promise.resolve(mockIssue);
    });

    vi.spyOn(apiClient, 'patch').mockResolvedValue(mockIssue);
    vi.spyOn(apiClient, 'post').mockResolvedValue({});
    vi.spyOn(apiClient, 'delete').mockResolvedValue({});
  });

  // Test Case 1: Split-pane IssueSurface renders Subscribe, Link Graph, and Overflow action slots.
  describe('Test Case 1: Split-pane IssueSurface Action Bar Parity', () => {
    it('renders Subscribe, Link Graph, and Overflow action slots inside split-action-toolbar', async () => {
      const mockSubscribeSlot = vi.fn(({ issue }: { issue: IssueDetail }) => (
        <button type="button" data-testid="split-slot-subscribe">
          Subscribe ({issue.key})
        </button>
      ));
      const mockLinkSlot = vi.fn(({ issue }: { issue: IssueDetail }) => (
        <button type="button" data-testid="split-slot-link">
          Link Graph ({issue.key})
        </button>
      ));
      const mockOverflowSlot = vi.fn(({ issue }: { issue: IssueDetail }) => (
        <button type="button" data-testid="split-slot-overflow">
          More Actions ({issue.key})
        </button>
      ));

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceSlotsContext.Provider
              value={{
                subscribe: mockSubscribeSlot,
                link: mockLinkSlot,
                overflow: mockOverflowSlot,
              }}
            >
              <IssueSurfaceRoot
                issueKey="KAN-100"
                projectKey="KAN"
                projectName="Platform Core"
                mode="split"
                issuesList={mockIssuesList}
                onClose={vi.fn()}
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
      });

      const toolbar = screen.getByTestId('split-action-toolbar');
      expect(toolbar.getAttribute('role')).toBe('toolbar');
      expect(toolbar.getAttribute('aria-label')).toBe('Issue actions');

      // Verify all 3 slots render inside toolbar
      expect(screen.getByTestId('split-slot-subscribe')).toBeDefined();
      expect(screen.getByTestId('split-slot-link')).toBeDefined();
      expect(screen.getByTestId('split-slot-overflow')).toBeDefined();

      // Verify slot render props
      expect(mockSubscribeSlot).toHaveBeenCalled();
      expect(mockLinkSlot).toHaveBeenCalled();
      expect(mockOverflowSlot).toHaveBeenCalled();

      // Verify split header and sequential pager navigation controls
      expect(screen.getByTestId('split-breadcrumb').textContent).toContain('Platform Core / KAN-100');
      expect(screen.getByTestId('issue-navigator-position').textContent).toBe('2 of 3');
      expect(screen.getByTestId('issue-prev-btn')).toBeDefined();
      expect(screen.getByTestId('issue-next-btn')).toBeDefined();
    });

    it('renders default concrete slot components (SubscribeAction, LinkGraphAction, IssueOverflowMenu) in split mode', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceSlotsContext.Provider
              value={{
                link: LinkGraphAction,
                overflow: IssueOverflowMenu,
              }}
            >
              <IssueSurfaceRoot
                issueKey="KAN-100"
                projectKey="KAN"
                mode="split"
                issuesList={mockIssuesList}
                onClose={vi.fn()}
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
      });

      // Default LinkGraphAction trigger renders inside split-action-toolbar
      const linkGraphTrigger = screen.getByTestId('link-graph-trigger');
      expect(linkGraphTrigger).toBeDefined();
      expect(linkGraphTrigger.textContent).toContain('🕸️');

      // Default IssueOverflowMenu trigger renders inside split-action-toolbar
      const overflowTrigger = screen.getByTestId('issue-overflow-trigger');
      expect(overflowTrigger).toBeDefined();
      expect(overflowTrigger.textContent).toContain('⋯');
    });
  });

  // Test Case 2: IssueHeader copy link button and Link Graph action render distinct glyphs and aria labels.
  describe('Test Case 2: Deduplication and Disambiguation of Action Controls', () => {
    it('visually and semantically distinguishes copy-issue-link-btn from LinkGraphAction', async () => {
      const clipboardMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: clipboardMock },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <IssueSurfaceSlotsContext.Provider
              value={{
                link: LinkGraphAction,
              }}
            >
              <IssueHeader
                issue={mockIssue}
                mode="drawer"
                onClose={vi.fn()}
                toggleFullScreen={vi.fn()}
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // 1. Copy issue link button (URL clipboard copy)
      const copyLinkBtn = screen.getByTestId('copy-issue-link-btn');
      expect(copyLinkBtn).toBeDefined();
      expect(copyLinkBtn.textContent).toContain('🔗');
      expect(copyLinkBtn.getAttribute('aria-label')).toBe('Copy issue link for KAN-100');
      expect(copyLinkBtn.getAttribute('title')).toBe('Copy issue link');

      // 2. LinkGraphAction trigger button (Object Graph relation manager)
      const linkGraphTrigger = screen.getByTestId('link-graph-trigger');
      expect(linkGraphTrigger).toBeDefined();
      expect(linkGraphTrigger.textContent).toContain('🕸️');
      expect(linkGraphTrigger.getAttribute('aria-label')).toBe('Link and Object Graph');
      expect(linkGraphTrigger.getAttribute('title')).toBe('Link and Object Graph');

      // 3. Strict disambiguation assertions: glyphs and labels must NOT collide
      expect(copyLinkBtn.textContent).not.toBe(linkGraphTrigger.textContent);
      expect(copyLinkBtn.getAttribute('aria-label')).not.toBe(linkGraphTrigger.getAttribute('aria-label'));
      expect(linkGraphTrigger.textContent).toBe('🕸️');

      // 4. Verify copy issue key button uses distinct 📋 clipboard glyph
      const copyKeyBtn = screen.getByTestId('copy-issue-key-btn');
      expect(copyKeyBtn.textContent).toContain('📋');
      expect(copyKeyBtn.getAttribute('aria-label')).toBe('Copy issue key KAN-100');

      // 5. Test clipboard action feedback
      fireEvent.click(copyLinkBtn);
      await waitFor(() => {
        expect(copyLinkBtn.textContent).toContain('Copied!');
      });
    });

    it('renders consistent fullscreen toggle ergonomics between IssueHeader and IssueOverflowMenu', () => {
      const toggleFullScreenMock = vi.fn();

      // Drawer mode
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <IssueHeader
              issue={mockIssue}
              mode="drawer"
              onClose={vi.fn()}
              toggleFullScreen={toggleFullScreenMock}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const headerFsBtnDrawer = screen.getByTestId('issue-header-fullscreen-toggle');
      expect(headerFsBtnDrawer.textContent).toContain('↗');
      expect(headerFsBtnDrawer.getAttribute('aria-label')).toBe('Open in full screen');

      fireEvent.click(headerFsBtnDrawer);
      expect(toggleFullScreenMock).toHaveBeenCalledTimes(1);
      unmount();

      // Fullscreen mode
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <IssueHeader
              issue={mockIssue}
              mode="full"
              onClose={vi.fn()}
              toggleFullScreen={toggleFullScreenMock}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const headerFsBtnFull = screen.getByTestId('issue-header-fullscreen-toggle');
      expect(headerFsBtnFull.textContent).toContain('↙');
      expect(headerFsBtnFull.getAttribute('aria-label')).toBe('Return to side panel');

      // Also verify overflow menu fullscreen toggle reflects the active mode
      const { unmount: unmountOverflow } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <IssueOverflowMenu
              issue={mockIssue}
              mode="full"
              toggleFullScreen={toggleFullScreenMock}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const overflowTrigger = screen.getByTestId('issue-overflow-trigger');
      fireEvent.click(overflowTrigger);

      const overflowFsBtn = screen.getByTestId('overflow-toggle-fullscreen-btn');
      expect(overflowFsBtn.textContent).toContain('↙');
      expect(overflowFsBtn.textContent).toContain('Return to side panel');
      expect(overflowFsBtn.getAttribute('aria-label')).toBe('Return to side panel');

      fireEvent.click(overflowFsBtn);
      expect(toggleFullScreenMock).toHaveBeenCalledTimes(2);
      unmountOverflow();
    });
  });

  // Test Case 3: Action slots in split mode execute mutations and update issue state correctly.
  describe('Test Case 3: Action Slots Mutations in Split Mode', () => {
    it('executes state transitions via split-state-select and updates issue state', async () => {
      const patchIssueSpy = vi.spyOn(railApi, 'patchIssue').mockResolvedValue({
        ...mockIssue,
        state: { id: 'state-in-progress', name: 'In Progress', group: 'started' },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceRoot
              issueKey="KAN-100"
              projectKey="KAN"
              mode="split"
              issuesList={mockIssuesList}
              onClose={vi.fn()}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-state-select')).toBeDefined();
      });

      const stateSelect = screen.getByTestId('split-state-select');
      fireEvent.change(stateSelect, { target: { value: 'state-in-progress' } });

      await waitFor(() => {
        expect(patchIssueSpy).toHaveBeenCalledWith(
          'KAN-100',
          { state_id: 'state-in-progress' },
          undefined,
        );
      });
    });

    it('executes 1-click self-assignment via split-assign-btn', async () => {
      const addAssigneeSpy = vi.spyOn(railApi, 'addAssignee').mockResolvedValue({
        id: 'asg-u-admin',
        kind: 'principal',
        principal: {
          id: 'u-admin',
          handle: 'admin',
          display_name: 'Administrator',
          type: 'USER',
        },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceRoot
              issueKey="KAN-100"
              projectKey="KAN"
              mode="split"
              issuesList={mockIssuesList}
              onClose={vi.fn()}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-assign-btn')).toBeDefined();
      });

      const assignBtn = screen.getByTestId('split-assign-btn');
      fireEvent.click(assignBtn);

      await waitFor(() => {
        expect(addAssigneeSpy).toHaveBeenCalledWith('KAN-100', { principal: 'u-admin' });
      });
    });

    it('toggles issue favorite state in localStorage and updates button label', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceRoot
              issueKey="KAN-100"
              projectKey="KAN"
              mode="split"
              issuesList={mockIssuesList}
              onClose={vi.fn()}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('favorite-issue-toggle')).toBeDefined();
      });

      const favToggle = screen.getByTestId('favorite-issue-toggle');
      expect(favToggle.textContent).toContain('☆ Favorite');

      fireEvent.click(favToggle);
      await waitFor(() => {
        expect(favToggle.textContent).toContain('★ Favorite');
      });
      expect(localStorage.getItem('kb_favorite_issues')).toContain('KAN-100');

      fireEvent.click(favToggle);
      await waitFor(() => {
        expect(favToggle.textContent).toContain('☆ Favorite');
      });
    });

    it('executes Object Graph link creation via LinkGraphAction slot', async () => {
      const createLinkSpy = vi.spyOn(actionsApi, 'createObjectLink').mockResolvedValue({
        id: 'lnk-test-1',
        link_type: 'RELATES_TO',
        link_state: 'ACTIVE',
        target: {
          id: 'obj-99',
          type: 'issue',
          key: 'KAN-99',
          title: 'Previous Work Item',
          restricted: false,
        },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceSlotsContext.Provider
              value={{
                link: LinkGraphAction,
              }}
            >
              <IssueSurfaceRoot
                issueKey="KAN-100"
                projectKey="KAN"
                mode="split"
                issuesList={mockIssuesList}
                onClose={vi.fn()}
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('link-graph-trigger')).toBeDefined();
      });

      const linkTrigger = screen.getByTestId('link-graph-trigger');
      fireEvent.click(linkTrigger);

      await waitFor(() => {
        expect(screen.getByTestId('link-graph-popover')).toBeDefined();
      });

      const targetInput = screen.getByTestId('link-target-input');
      const submitBtn = screen.getByTestId('add-link-submit-btn');

      fireEvent.change(targetInput, { target: { value: 'KAN-99' } });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(createLinkSpy).toHaveBeenCalledWith('KAN-100', 'KAN-99', 'RELATES_TO');
      });
    });

    it('triggers fullscreen transition from split-pane overflow menu slot', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-100']}>
            <IssueSurfaceSlotsContext.Provider
              value={{
                overflow: IssueOverflowMenu,
              }}
            >
              <IssueSurfaceRoot
                issueKey="KAN-100"
                projectKey="KAN"
                mode="split"
                issuesList={mockIssuesList}
                onClose={vi.fn()}
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('issue-overflow-trigger')).toBeDefined();
      });

      const overflowTrigger = screen.getByTestId('issue-overflow-trigger');
      fireEvent.click(overflowTrigger);

      const fsBtn = screen.getByTestId('overflow-toggle-fullscreen-btn');
      expect(fsBtn).toBeDefined();
      expect(fsBtn.textContent).toContain('Open in full screen');

      fireEvent.click(fsBtn);
      await waitFor(() => {
        expect(screen.queryByTestId('issue-overflow-menu')).toBeNull();
      });
    });
  });
});
