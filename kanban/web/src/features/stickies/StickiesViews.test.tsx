/**
 * Unit Tests for ProjectOverviewView & WorkspaceStickiesView (KB-P3-51, S8.1, S8.2).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProjectRouteContext } from '../../app/ProjectRouteContext';
import { ProjectOverviewView } from './ProjectOverviewView';
import { WorkspaceStickiesView } from './WorkspaceStickiesView';
import {
  resetStickiesCsrfCache,
  getStickiesCsrfToken,
  type StickyItem,
} from './stickiesApi';

const mockProjectStickies: StickyItem[] = [
  {
    id: 's-proj-1',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Project triage note',
    color_token: 'amber',
    sort_rank: '0',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 's-proj-2',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Second project note for promotion',
    color_token: 'mint',
    sort_rank: '1',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 's-proj-promoted',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Promoted specification note',
    color_token: 'slate',
    sort_rank: '2',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: 'doc-proj-1',
    is_promoted_stub: true,
    promoted_to_doc: {
      id: 'doc-proj-1',
      title: 'Promoted Spec',
    },
    triggers: [],
    capabilities: ['EDIT'],
  },
];

const mockWorkspaceStickies: StickyItem[] = [
  {
    id: 's-ws-1',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Workspace note',
    color_token: 'mint',
    sort_rank: '0',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 's-ws-2',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Second workspace note for promotion',
    color_token: 'sky',
    sort_rank: '1',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 's-ws-promoted',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Workspace promoted note',
    color_token: 'lavender',
    sort_rank: '2',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: 'doc-ws-1',
    is_promoted_stub: true,
    promoted_to_doc: {
      id: 'doc-ws-1',
      title: 'Workspace Spec Doc',
    },
    triggers: [],
    capabilities: ['EDIT'],
  },
];

describe('Stickies Views', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.restoreAllMocks();
    resetStickiesCsrfCache();
    document.cookie = 'kb_csrf=test-csrf-token; path=/';
  });

  describe('ProjectOverviewView', () => {
    it('handles query, creation, update, deletion, promote, and unarchive', async () => {
      globalThis.fetch = vi
        .fn()
        // 1. Initial list fetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ items: mockProjectStickies }),
        })
        // 2. Create sticky
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              id: 's-new',
              workspace_id: 'ws-1',
              project_id: 'proj-1',
              body_markdown: '',
              color_token: 'amber',
              sort_rank: '3',
              promotion_recommended: false,
              promotion_snoozed_at_length: null,
              promoted_to_doc_id: null,
              is_promoted_stub: false,
              triggers: [],
              capabilities: ['EDIT'],
            }),
        })
        // 3. Update sticky
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockProjectStickies[0],
              color_token: 'mint',
            }),
        })
        // 4. Delete sticky s-proj-1
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ deleted: true }),
        })
        // 5. Promote sticky s-proj-2
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockProjectStickies[1],
              promoted_to_doc_id: 'doc-promoted-new',
              is_promoted_stub: true,
            }),
        })
        // 6. Unarchive copy
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockProjectStickies[2],
              id: 's-copy',
              promoted_to_doc_id: null,
              is_promoted_stub: false,
            }),
        });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/overview']}>
            <Routes>
              <Route path="/projects/:projectKey/overview" element={<ProjectOverviewView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Project Overview Stickies')).toBeDefined();
      expect(await screen.findByTestId('sticky-card-s-proj-1')).toBeDefined();
      expect(await screen.findByTestId('sticky-card-s-proj-2')).toBeDefined();
      expect(await screen.findByTestId('promoted-sticky-stub-s-proj-promoted')).toBeDefined();

      // Create new sticky
      const newBtn = screen.getByRole('button', { name: 'Create new sticky note' });
      fireEvent.click(newBtn);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/projects/KAN/stickies',
          expect.objectContaining({ method: 'POST' }),
        );
      });

      // Update sticky color on s-proj-1
      const cardProj1 = screen.getByTestId('sticky-card-s-proj-1');
      const mintSwatch = within(cardProj1).getByRole('radio', { name: 'Color mint' });
      fireEvent.click(mintSwatch);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-proj-1',
          expect.objectContaining({ method: 'PATCH' }),
        );
      });

      // Delete sticky s-proj-1
      const menuTrigger1 = screen.getByTestId('sticky-menu-trigger-s-proj-1');
      fireEvent.click(menuTrigger1);
      const deleteItem = screen.getByTestId('delete-sticky-menuitem');
      fireEvent.click(deleteItem);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-proj-1',
          expect.objectContaining({ method: 'DELETE' }),
        );
      });

      // Promote sticky s-proj-2 via menu
      const menuTrigger2 = screen.getByTestId('sticky-menu-trigger-s-proj-2');
      fireEvent.click(menuTrigger2);
      const convertItem = screen.getByTestId('convert-to-doc-menuitem');
      fireEvent.click(convertItem);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-proj-2/promote-to-doc',
          expect.objectContaining({ method: 'POST' }),
        );
      });

      // Unarchive copy
      const promotedCard = screen.getByTestId('promoted-sticky-stub-s-proj-promoted');
      const unarchiveBtn = within(promotedCard).getByRole('button', { name: /Unarchive editable sticky copy/i });
      fireEvent.click(unarchiveBtn);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-proj-promoted/unarchive-copy',
          expect.objectContaining({ method: 'POST' }),
        );
      });
    });

    it('covers ProjectOverviewView read-only capabilities and fallback branches', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ items: [] }),
      });

      // 1. projectKey with VIEW-only capability -> canEdit is false, onCreateSticky is undefined
      const { unmount: u1 } = render(
        <QueryClientProvider client={queryClient}>
          <ProjectRouteContext.Provider
            value={{
              projectKey: 'KAN',
              projectName: 'Test Project',
              modulesEnabled: true,
              isProjectAdmin: false,
              capabilities: ['VIEW'],
            }}
          >
            <MemoryRouter initialEntries={['/projects/KAN/overview']}>
              <Routes>
                <Route path="/projects/:projectKey/overview" element={<ProjectOverviewView />} />
              </Routes>
            </MemoryRouter>
          </ProjectRouteContext.Provider>
        </QueryClientProvider>,
      );
      expect(await screen.findByTestId('project-overview-page')).toBeDefined();
      expect(screen.queryByTestId('new-sticky-btn')).toBeNull();
      u1();

      // 2. Empty projectKey with empty capabilities -> falls back to ['EDIT', 'ADMIN']
      const { unmount: u2 } = render(
        <QueryClientProvider client={queryClient}>
          <ProjectRouteContext.Provider
            value={{
              projectKey: '',
              projectName: 'Test Project',
              modulesEnabled: true,
              isProjectAdmin: false,
              capabilities: [],
            }}
          >
            <MemoryRouter initialEntries={['/projects/KAN/overview']}>
              <Routes>
                <Route path="/projects/:projectKey/overview" element={<ProjectOverviewView />} />
              </Routes>
            </MemoryRouter>
          </ProjectRouteContext.Provider>
        </QueryClientProvider>,
      );
      expect(await screen.findByTestId('project-overview-page')).toBeDefined();
      expect(screen.getByTestId('new-sticky-btn')).toBeDefined();
      u2();

      // 3. Empty projectKey with isProjectAdmin true
      const { unmount: u3 } = render(
        <QueryClientProvider client={queryClient}>
          <ProjectRouteContext.Provider
            value={{
              projectKey: '',
              projectName: 'Test Project',
              modulesEnabled: true,
              isProjectAdmin: true,
              capabilities: ['VIEW'],
            }}
          >
            <MemoryRouter initialEntries={['/projects/KAN/overview']}>
              <Routes>
                <Route path="/projects/:projectKey/overview" element={<ProjectOverviewView />} />
              </Routes>
            </MemoryRouter>
          </ProjectRouteContext.Provider>
        </QueryClientProvider>,
      );
      expect(await screen.findByTestId('project-overview-page')).toBeDefined();
      expect(screen.getByTestId('new-sticky-btn')).toBeDefined();
      u3();
    });
  });

  describe('WorkspaceStickiesView', () => {
    it('handles query, update, deletion, promote, and unarchive across workspace', async () => {
      globalThis.fetch = vi
        .fn()
        // 1. Initial list fetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ items: mockWorkspaceStickies }),
        })
        // 2. Update sticky s-ws-1
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockWorkspaceStickies[0],
              color_token: 'sky',
            }),
        })
        // 3. Delete sticky s-ws-1
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ deleted: true }),
        })
        // 4. Promote sticky s-ws-2
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockWorkspaceStickies[1],
              promoted_to_doc_id: 'doc-ws-promoted-new',
              is_promoted_stub: true,
            }),
        })
        // 5. Unarchive copy
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve({
              ...mockWorkspaceStickies[2],
              id: 's-ws-copy',
              promoted_to_doc_id: null,
              is_promoted_stub: false,
            }),
        });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/stickies']}>
            <Routes>
              <Route path="/stickies" element={<WorkspaceStickiesView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('Workspace Stickies')).toBeDefined();
      expect(await screen.findByTestId('sticky-card-s-ws-1')).toBeDefined();
      expect(await screen.findByTestId('sticky-card-s-ws-2')).toBeDefined();
      expect(await screen.findByTestId('promoted-sticky-stub-s-ws-promoted')).toBeDefined();

      // Update sticky color on s-ws-1
      const cardWs1 = screen.getByTestId('sticky-card-s-ws-1');
      const skySwatch = within(cardWs1).getByRole('radio', { name: 'Color sky' });
      fireEvent.click(skySwatch);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-ws-1',
          expect.objectContaining({ method: 'PATCH' }),
        );
      });

      // Delete sticky s-ws-1
      const menuTrigger1 = screen.getByTestId('sticky-menu-trigger-s-ws-1');
      fireEvent.click(menuTrigger1);
      const deleteItem = screen.getByTestId('delete-sticky-menuitem');
      fireEvent.click(deleteItem);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-ws-1',
          expect.objectContaining({ method: 'DELETE' }),
        );
      });

      // Promote sticky s-ws-2
      const menuTrigger2 = screen.getByTestId('sticky-menu-trigger-s-ws-2');
      fireEvent.click(menuTrigger2);
      const convertItem = screen.getByTestId('convert-to-doc-menuitem');
      fireEvent.click(convertItem);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-ws-2/promote-to-doc',
          expect.objectContaining({ method: 'POST' }),
        );
      });

      // Unarchive copy
      const promotedCard = screen.getByTestId('promoted-sticky-stub-s-ws-promoted');
      const unarchiveBtn = within(promotedCard).getByRole('button', { name: /Unarchive editable sticky copy/i });
      fireEvent.click(unarchiveBtn);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/stickies/s-ws-promoted/unarchive-copy',
          expect.objectContaining({ method: 'POST' }),
        );
      });
    });

    it('renders + New Sticky in header and empty state and bootstraps CSRF from /api/v1/auth/session', async () => {
      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      resetStickiesCsrfCache();
      expect(getStickiesCsrfToken()).toBeNull();

      const createdSticky: StickyItem = {
        id: 's-ws-created',
        workspace_id: 'ws-1',
        project_id: 'proj-1',
        body_markdown: '',
        color_token: 'amber',
        sort_rank: '0',
        promotion_recommended: false,
        promotion_snoozed_at_length: null,
        promoted_to_doc_id: null,
        is_promoted_stub: false,
        triggers: [],
        capabilities: ['EDIT', 'DELETE'],
      };

      globalThis.fetch = vi
        .fn()
        // 1. Initial empty workspace stickies fetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        })
        // 2. CSRF bootstrap from /api/v1/auth/session
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ authenticated: true, csrf_token: 'bootstrapped-csrf-999' }),
        })
        // 3. Create sticky via empty state button
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(createdSticky),
        })
        // 4. Create second sticky via header + New Sticky button (uses cached CSRF token)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ ...createdSticky, id: 's-ws-created-2' }),
        });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/stickies']}>
            <Routes>
              <Route path="/stickies" element={<WorkspaceStickiesView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('No stickies yet')).toBeDefined();
      const headerNewBtn = screen.getByTestId('new-sticky-btn');
      expect(headerNewBtn).toBeDefined();

      const emptyCreateBtn = screen.getByRole('button', { name: '+ Create your first sticky' });
      fireEvent.click(emptyCreateBtn);

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/auth/session',
          expect.objectContaining({ method: 'GET', credentials: 'same-origin' }),
        );
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/projects/KAN/stickies',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'X-CSRF-Token': 'bootstrapped-csrf-999',
            }) as unknown as Record<string, string>,
          }),
        );
      });

      expect(await screen.findByTestId('sticky-card-s-ws-created')).toBeDefined();

      // Click header + New Sticky button
      fireEvent.click(headerNewBtn);
      await waitFor(() => {
        expect( screen.getByTestId('sticky-card-s-ws-created-2')).toBeDefined();
      });
    });

    it('falls back to first project from /api/v1/projects if default project KAN returns 404 on create', async () => {
      const createdSticky: StickyItem = {
        id: 's-ws-fallback-proj',
        workspace_id: 'ws-1',
        project_id: 'proj-qa',
        body_markdown: '',
        color_token: 'amber',
        sort_rank: '0',
        promotion_recommended: false,
        promotion_snoozed_at_length: null,
        promoted_to_doc_id: null,
        is_promoted_stub: false,
        triggers: [],
        capabilities: ['EDIT', 'DELETE'],
      };

      globalThis.fetch = vi
        .fn()
        // 1. Initial empty workspace stickies fetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        })
        // 2. First POST to /api/v1/projects/KAN/stickies returns 404
        .mockResolvedValueOnce({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ detail: 'Project not found' }),
        })
        // 3. Fallback GET /api/v1/projects returns QA project
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ items: [{ identifier: 'QA' }] }),
        })
        // 4. Retry POST to /api/v1/projects/QA/stickies succeeds
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(createdSticky),
        });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/stickies']}>
            <Routes>
              <Route path="/stickies" element={<WorkspaceStickiesView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('No stickies yet')).toBeDefined();
      fireEvent.click(screen.getByTestId('new-sticky-btn'));

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/projects/QA/stickies',
          expect.objectContaining({ method: 'POST' }),
        );
      });
      expect(await screen.findByTestId('sticky-card-s-ws-fallback-proj')).toBeDefined();
    });

    it('renders WorkspaceStickiesView in readOnly mode without new sticky button', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ items: [] }),
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/stickies']}>
            <Routes>
              <Route path="/stickies" element={<WorkspaceStickiesView readOnly={true} />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByText('No stickies yet')).toBeDefined();
      expect(screen.queryByTestId('new-sticky-btn')).toBeNull();
    });
  });
});
