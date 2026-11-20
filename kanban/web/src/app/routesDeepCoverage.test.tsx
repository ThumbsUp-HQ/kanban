import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ThemeProvider } from '../theme/ThemeProvider';
import * as client from '../api/client';
import {
  saveDraft,
} from '../features/drafts/draftsStore';
import {
  DraftsWorkspaceView,
  ProjectCyclesView,
  ProjectModulesView,
  ProjectSavedViewsView,
  ProjectViewsRedirect,
  FullScreenIssueRoute,
  WorkspaceHomeView,
  RoutePlaceholder,
  NotFoundView,
  DevStoryRoute,
  AdminRouteGuard,
  DraftsWorkspaceRouteGuard,
  ProjectRouteContainer,
  ProjectDocPageRoute,
  ProjectDocsRoute,
  ProjectOverviewRoute,
  ProjectIssueDetailRoute,
} from './routes';

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('routesDeepCoverage', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  describe('DraftsWorkspaceView detailed branches', () => {
    it('covers state name matching, module matching, description/priority, and network fallback', async () => {
      saveDraft({
        id: 'draft-match-name',
        projectKey: 'KAN',
        summary: 'Draft with state name match',
        description: 'Detailed description markdown',
        prioritySlug: 'urgent',
        stateId: 'state-in-progress',
        moduleIds: ['mod-1', 'mod-invalid'],
      });

      saveDraft({
        id: 'draft-match-id',
        projectKey: 'KAN',
        summary: 'Draft with direct id match',
        stateId: 's-done',
        prioritySlug: 'medium',
        moduleIds: [],
      });

      saveDraft({
        id: 'draft-no-fields',
        projectKey: 'KAN',
        summary: 'Plain draft',
        stateId: 's-todo',
        prioritySlug: 'low',
      });

      const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        const method = init?.method ?? 'GET';

        if (url.includes('/api/v1/projects/KAN/states') && method === 'GET') {
          return Promise.resolve(
            jsonResponse([
              { id: 's-in-prog', name: 'In Progress', group: 'started' },
              { id: 's-done', name: 'Done', group: 'completed' },
            ]),
          );
        }

        if (url.includes('/api/v1/projects/KAN/modules') && method === 'GET') {
          return Promise.resolve(
            jsonResponse([
              { id: 'mod-1', name: 'Security Vault' },
            ]),
          );
        }

        if (url.includes('/api/v1/projects/KAN/issues') && method === 'POST') {
          return Promise.resolve(
            jsonResponse({ key: 'KAN-101' }, 201),
          );
        }

        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <MemoryRouter initialEntries={['/drafts']}>
          <DraftsWorkspaceView />
        </MemoryRouter>,
      );

      expect(screen.getAllByTestId('draft-card')).toHaveLength(3);
      expect(screen.getByText('Priority: urgent')).toBeDefined();
      expect(screen.getByText('Detailed description markdown')).toBeDefined();

      // Resume draft 1 (name match + modules)
      const resumeButtons = screen.getAllByTestId('draft-resume-btn');
      const firstResumeBtn = resumeButtons[0];
      if (firstResumeBtn) {
        fireEvent.click(firstResumeBtn);
      }

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      unmount();
    });

    it('handles state & module endpoint exceptions and post issue fallback navigation', async () => {
      saveDraft({
        id: 'draft-fallback',
        projectKey: 'KAN',
        summary: 'Fallback draft',
        stateId: 'st-missing',
        prioritySlug: 'urgent',
        moduleIds: ['mod-x'],
      });

      vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        const method = init?.method ?? 'GET';

        if (url.includes('/api/v1/projects/KAN/states')) {
          return Promise.reject(new Error('States offline'));
        }
        if (url.includes('/api/v1/projects/KAN/modules')) {
          return Promise.reject(new Error('Modules offline'));
        }
        if (url.includes('/api/v1/projects/KAN/issues') && method === 'POST') {
          return Promise.reject(new Error('Post issues failed'));
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <MemoryRouter initialEntries={['/drafts']}>
          <DraftsWorkspaceView />
        </MemoryRouter>,
      );

      const resumeBtn = screen.getByTestId('draft-resume-btn');
      fireEvent.click(resumeBtn);

      await waitFor(() => {
        expect(screen.getByTestId('drafts-empty')).toBeDefined();
      });

      unmount();
    });
  });

  describe('ProjectCyclesView detailed branches', () => {
    it('covers status labels, date validation, create, edit, complete rollover, and delete', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      let cycleItems = [
        {
          id: 'c-1',
          name: 'Sprint Alpha',
          status: 'in_progress',
          start_date: '2026-01-01',
          end_date: '2026-01-14',
        },
        {
          id: 'c-2',
          name: 'Sprint Beta',
          status: 'planned',
          start_date: '2026-01-15',
          end_date: '2026-01-28',
        },
        {
          id: 'c-3',
          name: 'Sprint Gamma',
          status: 'completed',
          start_date: '2025-12-01',
          end_date: '2025-12-14',
        },
        {
          id: 'c-4',
          name: 'Sprint Delta',
          status: 'backlog',
        },
        {
          id: 'c-5',
          name: 'Sprint Epsilon',
          status: 'paused',
        },
        {
          id: 'c-6',
          name: 'Sprint Zeta',
          status: 'cancelled',
        },
        {
          id: 'c-7',
          name: 'Sprint Eta',
          status: 'custom_state',
        },
        {
          id: 'c-8',
          name: 'Sprint Theta',
          status: '',
        },
      ];

      vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        const method = init?.method ?? 'GET';

        if (url.includes('/api/v1/projects/KAN') && !url.includes('/cycles') && method === 'GET') {
          return Promise.resolve(
            jsonResponse({ capabilities: ['ADMIN', 'PROJECT_ADMIN', 'EDIT'] }),
          );
        }

        if (url.includes('/api/v1/projects/KAN/cycles') && method === 'GET') {
          return Promise.resolve(jsonResponse({ items: cycleItems }));
        }

        if (url.includes('/api/v1/projects/KAN/cycles') && method === 'POST') {
          const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as {
            name?: string;
            start_date?: string | null;
            end_date?: string | null;
          };
          const newCycle = {
            id: 'c-9',
            name: body.name ?? '',
            status: 'upcoming',
            start_date: body.start_date ?? '2026-06-01',
            end_date: body.end_date ?? '2026-06-30',
          };
          cycleItems.push(newCycle);
          return Promise.resolve(jsonResponse(newCycle, 201));
        }

        if (url.includes('/api/v1/cycles/c-1/complete') && method === 'POST') {
          return Promise.resolve(jsonResponse({ ok: true }));
        }

        if (url.includes('/api/v1/cycles/c-1') && method === 'PATCH') {
          const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as {
            name?: string;
            start_date?: string | null;
            end_date?: string | null;
          };
          return Promise.resolve(
            jsonResponse({
              id: 'c-1',
              name: body.name ?? '',
              status: 'in_progress',
              start_date: body.start_date ?? null,
              end_date: body.end_date ?? null,
            }),
          );
        }

        if (url.includes('/api/v1/cycles/c-2') && method === 'DELETE') {
          cycleItems = cycleItems.filter((c) => c.id !== 'c-2');
          return Promise.resolve(jsonResponse({ ok: true }));
        }

        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <ProjectCyclesView capabilities={['ADMIN', 'PROJECT_ADMIN', 'EDIT']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Verify all status types formatted
      await waitFor(() => {
        expect(screen.getByText('Sprint Alpha')).toBeDefined();
      });
      expect(screen.getByText('In Progress')).toBeDefined();
      expect(screen.getByText('Planned')).toBeDefined();
      expect(screen.getByText('Completed')).toBeDefined();
      expect(screen.getByText('Backlog')).toBeDefined();
      expect(screen.getByText('Paused')).toBeDefined();
      expect(screen.getByText('Cancelled')).toBeDefined();
      expect(screen.getByText('Custom state')).toBeDefined();
      expect(screen.getByText('Upcoming')).toBeDefined();

      // 1. Create cycle with invalid date order
      fireEvent.change(screen.getByTestId('new-cycle-name-input'), { target: { value: 'Inverted Sprint' } });
      fireEvent.change(screen.getByTestId('new-cycle-start-input'), { target: { value: '2026-05-10' } });
      fireEvent.change(screen.getByTestId('new-cycle-end-input'), { target: { value: '2026-05-01' } });
      fireEvent.click(screen.getByTestId('create-cycle-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('cycle-error-banner')).toBeDefined();
      });
      expect(screen.getByText('End date cannot be earlier than start date.')).toBeDefined();

      // Create cycle with valid dates
      fireEvent.change(screen.getByTestId('new-cycle-end-input'), { target: { value: '2026-05-20' } });
      fireEvent.click(screen.getByTestId('create-cycle-btn'));

      // 2. Edit cycle
      fireEvent.click(screen.getByTestId('edit-cycle-btn-c-1'));
      expect(screen.getByTestId('edit-cycle-modal')).toBeDefined();

      // Invalid date in edit
      fireEvent.change(screen.getByTestId('edit-cycle-start-input'), { target: { value: '2026-06-10' } });
      fireEvent.change(screen.getByTestId('edit-cycle-end-input'), { target: { value: '2026-06-01' } });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('edit-cycle-error')).toBeDefined();
      });

      // Valid date in edit
      fireEvent.change(screen.getByTestId('edit-cycle-end-input'), { target: { value: '2026-06-20' } });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

      // 3. Complete cycle with rollover
      fireEvent.click(screen.getByTestId('complete-cycle-btn-c-1'));
      expect(screen.getByTestId('complete-cycle-modal')).toBeDefined();

      fireEvent.change(screen.getByTestId('rollover-target-select'), { target: { value: 'c-2' } });
      fireEvent.click(screen.getByTestId('confirm-complete-cycle-btn'));

      // 4. Delete cycle
      fireEvent.click(screen.getByTestId('delete-cycle-btn-c-2'));

      unmount();
    });
  });

  describe('ProjectModulesView detailed branches', () => {
    it('covers date validation, create, edit, and delete', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      let moduleItems = [
        {
          id: 'm-1',
          name: 'Auth Module',
          status: 'planned',
          start_date: '2026-01-01',
          target_date: '2026-02-01',
          description_markdown: 'Authentication features',
        },
      ];

      vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        const method = init?.method ?? 'GET';

        if (url.includes('/api/v1/projects/KAN') && !url.includes('/modules') && method === 'GET') {
          return Promise.resolve(
            jsonResponse({ capabilities: ['ADMIN', 'PROJECT_ADMIN', 'EDIT'] }),
          );
        }

        if (url.includes('/api/v1/projects/KAN/modules') && method === 'GET') {
          return Promise.resolve(jsonResponse({ items: moduleItems }));
        }

        if (url.includes('/api/v1/projects/KAN/modules') && method === 'POST') {
          const body = JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as {
            name?: string;
            status?: string;
            start_date?: string | null;
            target_date?: string | null;
            description_markdown?: string | null;
          };
          const newMod = {
            id: 'm-2',
            name: body.name ?? '',
            status: body.status ?? 'planned',
            start_date: body.start_date ?? '2026-06-01',
            target_date: body.target_date ?? '2026-06-30',
            description_markdown: body.description_markdown ?? '',
          };
          moduleItems.push(newMod);
          return Promise.resolve(jsonResponse(newMod, 201));
        }

        if (url.includes('/api/v1/modules/m-1') && method === 'PATCH') {
          return Promise.resolve(jsonResponse({ id: 'm-1', name: 'Updated Auth' }));
        }

        if (url.includes('/api/v1/modules/m-1') && method === 'DELETE') {
          moduleItems = [];
          return Promise.resolve(jsonResponse({ ok: true }));
        }

        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <ProjectModulesView capabilities={['ADMIN', 'PROJECT_ADMIN', 'EDIT']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Auth Module')).toBeDefined();
      });

      // 1. Create with invalid date order (start_date > target_date)
      fireEvent.change(screen.getByTestId('new-module-name-input'), { target: { value: 'Billing' } });
      fireEvent.change(screen.getByTestId('new-module-start-input'), { target: { value: '2026-05-10' } });
      fireEvent.change(screen.getByTestId('new-module-target-input'), { target: { value: '2026-05-01' } });
      fireEvent.change(screen.getByTestId('new-module-desc-input'), { target: { value: 'Billing module desc' } });
      fireEvent.click(screen.getByTestId('create-module-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('module-error-banner')).toBeDefined();
      });
      expect(screen.getByText('Target date cannot be earlier than start date.')).toBeDefined();

      // Create with valid target date
      fireEvent.change(screen.getByTestId('new-module-target-input'), { target: { value: '2026-05-30' } });
      fireEvent.click(screen.getByTestId('create-module-btn'));

      // 2. Edit module
      fireEvent.click(screen.getByTestId('edit-module-btn-m-1'));
      expect(screen.getByTestId('edit-module-modal')).toBeDefined();

      // Edit with invalid target date
      fireEvent.change(screen.getByTestId('edit-module-start-input'), { target: { value: '2026-07-10' } });
      fireEvent.change(screen.getByTestId('edit-module-target-input'), { target: { value: '2026-07-01' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('edit-module-error')).toBeDefined();
      });

      // Edit valid
      fireEvent.change(screen.getByTestId('edit-module-target-input'), { target: { value: '2026-07-20' } });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));

      // 3. Delete module
      fireEvent.click(screen.getByTestId('delete-module-btn-m-1'));

      unmount();
    });
  });

  describe('Placeholders and misc views', () => {
    it('renders RoutePlaceholder and NotFoundView (both routed and static)', () => {
      const { unmount: u1 } = render(<RoutePlaceholder route="/dev/test" />);
      expect(screen.getByText('Route: /dev/test')).toBeDefined();
      u1();

      // Routed NotFoundView
      const { unmount: u2 } = render(
        <MemoryRouter>
          <NotFoundView />
        </MemoryRouter>,
      );
      expect(screen.getByText('404')).toBeDefined();
      expect(screen.getByText('Return to Workspace')).toBeDefined();
      fireEvent.click(screen.getByTestId('return-workspace-btn'));
      u2();

      // Static NotFoundView (outside router context)
      const { unmount: u3 } = render(<NotFoundView />);
      expect(screen.getByText('404')).toBeDefined();
      fireEvent.click(screen.getByTestId('return-workspace-btn'));
      u3();
    });

    it('covers ProjectViewsRedirect and ProjectSavedViewsView', () => {
      const { unmount: u1 } = render(
        <MemoryRouter initialEntries={['/projects/views']}>
          <ProjectViewsRedirect />
        </MemoryRouter>,
      );
      u1();

      const { unmount: u2 } = render(
        <MemoryRouter initialEntries={['/projects/KAN/views']}>
          <ProjectSavedViewsView />
        </MemoryRouter>,
      );
      expect(screen.getByText('Views (KAN)')).toBeDefined();
      expect(screen.getByText('List View')).toBeDefined();
      expect(screen.getByText('Board View')).toBeDefined();
      u2();
    });

    it('covers FullScreenIssueRoute document title and query', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/issues/')) {
          return Promise.resolve(
            jsonResponse({
              key: 'KAN-142',
              summary: 'Hardened Fullscreen Title',
              state: { id: 's-1', name: 'In Progress', group: 'started' },
              capabilities: ['EDIT', 'ADMIN'],
            }),
          );
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
            <Routes>
              <Route path="/projects/:projectKey/issues/:issueKey" element={<FullScreenIssueRoute />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(document.title).toContain('KAN-142');
      });
      unmount();
    });

    it('covers DevStoryRoute for all developer story paths and fallback', () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const paths = [
        '/__dev/tokens',
        '/__dev/emoji',
        '/__dev/editor',
        '/__dev/media',
        '/__dev/realtime',
        '/__dev/drawer',
        '/__dev/drawer-rail',
        '/__dev/rail',
        '/__dev/drawer-actions',
        '/__dev/stickies',
        '/__dev/icons',
        '/__dev/unknown-story',
      ];

      for (const p of paths) {
        const { unmount } = render(
          <QueryClientProvider client={qc}>
            <ThemeProvider>
              <MemoryRouter initialEntries={[p]}>
                <DevStoryRoute />
              </MemoryRouter>
            </ThemeProvider>
          </QueryClientProvider>,
        );
        unmount();
      }
    });

    it('covers WorkspaceHomeView under different query client contexts and member roles', async () => {
      // 1. Without QueryClient
      const { unmount: u1 } = render(
        <MemoryRouter>
          <WorkspaceHomeView />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('route-placeholder')).toBeDefined();
      u1();

      // 2. With QueryClient, currentUser as VIEWER and projects with admin capabilities
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve(
            jsonResponse({
              workspace_role: 'VIEWER',
              is_server_admin: false,
              is_workspace_admin: false,
            }),
          );
        }
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(
            jsonResponse([
              {
                id: 'p-1',
                identifier: 'KAN',
                name: 'Core Kanban',
                capabilities: ['ADMIN', 'EDIT'],
                is_project_admin: true,
              },
            ]),
          );
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount: u2 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <WorkspaceHomeView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText(/Core Kanban/)).toBeDefined();
      });
      expect(screen.getByText('Custom Fields')).toBeDefined();
      u2();
    });

    it('covers AdminRouteGuard loading, forbidden, and multiple AAL2 formats', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      let mockUser: unknown = null;
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve(jsonResponse(mockUser));
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      // 1. Non-admin
      mockUser = { is_server_admin: false, aal_level: 1 };
      const { unmount: u1 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/admin']}>
            <Routes>
              <Route path="/admin" element={<AdminRouteGuard />}>
                <Route index element={<div data-testid="admin-content">Admin Content</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('404')).toBeDefined();
      });
      u1();

      // 2. Admin with string '2', 'aal2', and auth_aal 'aal2'
      const aalVariants = [
        { is_server_admin: true, aal_level: 2 },
        { is_server_admin: true, aal_level: '2' },
        { is_server_admin: true, aal_level: 'aal2' },
        { is_server_admin: true, aal_level: 1, auth_aal: 'aal2' },
      ];

      for (const variant of aalVariants) {
        mockUser = variant;
        const freshQc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
        const { unmount } = render(
          <QueryClientProvider client={freshQc}>
            <MemoryRouter initialEntries={['/admin']}>
              <Routes>
                <Route path="/admin" element={<AdminRouteGuard />}>
                  <Route index element={<div data-testid="admin-content">Admin Content</div>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </QueryClientProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('admin-content')).toBeDefined();
        });
        unmount();
      }
    });

    it('covers DraftsWorkspaceRouteGuard viewer fallback and member allow', async () => {
      let mockUser: unknown = { workspace_role: 'WORKSPACE_GUEST' };
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve(jsonResponse(mockUser));
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      // Guest -> 404
      const qc1 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: u1 } = render(
        <QueryClientProvider client={qc1}>
          <MemoryRouter>
            <DraftsWorkspaceRouteGuard />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('404')).toBeDefined();
      });
      u1();

      // Member -> DraftsWorkspaceView
      mockUser = { workspace_role: 'WORKSPACE_MEMBER' };
      const qc2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: u2 } = render(
        <QueryClientProvider client={qc2}>
          <MemoryRouter>
            <DraftsWorkspaceRouteGuard />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('drafts-view')).toBeDefined();
      });
      u2();
    });

    it('covers ProjectRouteContainer validation failures and direct route components', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      // Direct route components
      const { unmount: uDirect1 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter><ProjectIssueDetailRoute /></MemoryRouter>
        </QueryClientProvider>,
      );
      uDirect1();
      const { unmount: uDirect2 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter><ProjectOverviewRoute /></MemoryRouter>
        </QueryClientProvider>,
      );
      uDirect2();
      const { unmount: uDirect3 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter><ProjectDocsRoute /></MemoryRouter>
        </QueryClientProvider>,
      );
      uDirect3();
      const { unmount: uDirect4 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter><ProjectDocPageRoute /></MemoryRouter>
        </QueryClientProvider>,
      );
      uDirect4();

      // Invalid project key
      const { unmount: uInvalid } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/invalid_project/issues']}>
            <Routes>
              <Route path="/projects/:projectKey/issues" element={<ProjectRouteContainer />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByText('404')).toBeDefined();
      uInvalid();

      // Project not found response (404 / 403)
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/projects/NONEXISTENT')) {
          return Promise.resolve(jsonResponse({ error: 'Not found' }, 404));
        }
        return Promise.resolve(jsonResponse({ error: 'Internal Error' }, 500));
      });

      const { unmount: u404 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/NONEXISTENT/issues']}>
            <Routes>
              <Route path="/projects/:projectKey/issues" element={<ProjectRouteContainer />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('404')).toBeDefined();
      });
      u404();
    });

    it('covers NotFoundView without Router context (static view) and path fallback', () => {
      const originalLocation = window.location;
      let assignedHref = '';
      Object.defineProperty(window, 'location', {
        writable: true,
        value: {
          pathname: '',
          set href(val: string) {
            assignedHref = val;
          },
          get href() {
            return assignedHref;
          },
        },
      });

      const { unmount } = render(<NotFoundView />);
      expect(screen.getByTestId('not-found-path').textContent).toBe('unknown');
      const btn = screen.getByTestId('return-workspace-btn');
      fireEvent.click(btn);
      expect(assignedHref).toBe('/');
      unmount();

      Object.defineProperty(window, 'location', {
        writable: true,
        value: originalLocation,
      });
    });

    it('covers WorkspaceHomeView for VIEWER and non-admin workspace roles', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve(
            jsonResponse({
              id: 'u-viewer',
              handle: 'viewer',
              display_name: 'Viewer User',
              workspace_role: 'VIEWER',
              is_workspace_admin: false,
              is_server_admin: false,
            }),
          );
        }
        if (url.includes('/api/v1/projects') && !url.includes('/api/v1/projects/')) {
          return Promise.resolve(
            jsonResponse([
              {
                id: 'p-1',
                identifier: 'KAN',
                name: 'Project KAN',
                capabilities: ['ADMIN'],
                is_project_admin: true,
              },
            ]),
          );
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <WorkspaceHomeView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('project-card-KAN')).toBeDefined();
      });
      unmount();
    });

    it('covers ProjectCyclesView edit date validation error and empty completion', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/projects/KAN/cycles')) {
          return Promise.resolve(
            jsonResponse([
              { id: 'cyc-1', name: 'Sprint 1', status: 'active', start_date: '2026-05-10', end_date: '2026-05-20' },
            ]),
          );
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <ProjectCyclesView capabilities={['ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('cycle-item-cyc-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('edit-cycle-btn-cyc-1'));
      expect(screen.getByTestId('edit-cycle-modal')).toBeDefined();

      // Set end date earlier than start date
      fireEvent.change(screen.getByTestId('edit-cycle-start-input'), { target: { value: '2026-06-15' } });
      fireEvent.change(screen.getByTestId('edit-cycle-end-input'), { target: { value: '2026-06-01' } });
      const cycleForm = screen.getByTestId('edit-cycle-modal').querySelector('form');
      if (cycleForm) fireEvent.submit(cycleForm);

      await waitFor(() => {
        expect(screen.getByTestId('edit-cycle-error')).toBeDefined();
      });

      unmount();
    });

    it('covers ProjectModulesView edit date validation error and empty name', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/projects/KAN/modules')) {
          return Promise.resolve(
            jsonResponse([
              { id: 'mod-1', name: 'Auth Module', status: 'planned', start_date: '2026-04-01', target_date: '2026-04-30' },
            ]),
          );
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <ProjectModulesView capabilities={['ADMIN']} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('module-item-mod-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('edit-module-btn-mod-1'));
      expect(screen.getByTestId('edit-module-modal')).toBeDefined();

      // Set target date earlier than start date
      fireEvent.change(screen.getByTestId('edit-module-start-input'), { target: { value: '2026-05-15' } });
      fireEvent.change(screen.getByTestId('edit-module-target-input'), { target: { value: '2026-05-01' } });
      const modForm = screen.getByTestId('edit-module-modal').querySelector('form');
      if (modForm) fireEvent.submit(modForm);

      await waitFor(() => {
        expect(screen.getByTestId('edit-module-error')).toBeDefined();
      });

      unmount();
    });
  });

  describe('targeted branch coverage boosters for routes.tsx', () => {
    it('covers NotFoundView rendered outside router context', () => {
      render(<NotFoundView />);
      expect(screen.getByText(/Page Not Found/)).toBeDefined();
      fireEvent.click(screen.getByText('Return to Workspace'));
    });

    it('covers WorkspaceHomeView non-admin role and empty wrapped items fallback', async () => {
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve(
            jsonResponse({
              id: 'u-user',
              workspace_role: 'GUEST_CONTRIBUTOR',
              is_workspace_admin: false,
              is_server_admin: false,
            }),
          );
        }
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(jsonResponse({}));
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      render(
        <MemoryRouter initialEntries={['/']}>
          <WorkspaceHomeView />
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('route-placeholder')).toBeDefined();
      });
    });

    it('covers AdminRouteGuard access denied for non-admin user', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/auth/me') || url.includes('/api/v1/auth/session')) {
          return Promise.resolve(
            jsonResponse({
              id: 'u-std',
              is_server_admin: false,
              is_workspace_admin: false,
              aal_level: 1,
            }),
          );
        }
        return Promise.resolve(jsonResponse({ ok: true }));
      });

      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/admin/oauth']}>
            <Routes>
              <Route
                path="/admin/oauth"
                element={
                  <AdminRouteGuard>
                    <div data-testid="admin-content">Secret</div>
                  </AdminRouteGuard>
                }
              />
              <Route path="/" element={<div data-testid="home-fallback">Home</div>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('not-found-view')).toBeDefined();
      });
    });

    it('covers FullScreenIssueRoute query with valid issueKey and summary', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(client.apiClient, 'get').mockResolvedValueOnce({
        id: 'iss-1',
        key: 'KAN-999',
        summary: 'Deep Issue Detail',
      });
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-999']}>
            <Routes>
              <Route path="/projects/:projectKey/issues/:issueKey" element={<FullScreenIssueRoute />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(document.title).toBe('KAN-999 - Deep Issue Detail');
      });
    });

    it('covers ProjectRouteContainer with 500 error returning null', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects/KAN')) {
          return Promise.resolve(new Response('Server Error', { status: 500 }));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      });
      render(
        <QueryClientProvider client={qc}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/projects/KAN']}>
              <Routes>
                <Route path="/projects/:projectKey" element={<ProjectRouteContainer />} />
              </Routes>
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.queryByTestId('not-found-view')).toBeNull();
      });
    });

    it('covers ProjectRouteContainer with 403 error returning isNotFound', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/v1/projects/KAN')) {
          return Promise.resolve(new Response('Forbidden', { status: 403 }));
        }
        return Promise.resolve(new Response('{}', { status: 200 }));
      });
      render(
        <QueryClientProvider client={qc}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/projects/KAN']}>
              <Routes>
                <Route path="/projects/:projectKey" element={<ProjectRouteContainer />} />
              </Routes>
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('not-found-view')).toBeDefined();
      });
    });

    it('covers ProjectRouteContainer with missing identifier falling back to projectKey', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(window, 'fetch').mockResolvedValueOnce(
        jsonResponse({
          id: 'p-1',
          name: 'Fallback Project',
          modules_enabled: false,
          capabilities: ['VIEW'],
          is_project_admin: false,
        }),
      );
      render(
        <QueryClientProvider client={qc}>
          <ThemeProvider>
            <MemoryRouter initialEntries={['/projects/KAN']}>
              <Routes>
                <Route path="/projects/:projectKey" element={<ProjectRouteContainer />} />
              </Routes>
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.queryByTestId('not-found-view')).toBeNull();
      });
    });
  });
});

