/**
 * Dedicated Edge Tests for routes.tsx (KANBA-211, KANBA-212, KANBA-217).
 * Covers DevStoryRoute, ProjectRouteContainer, formatStatusLabel, and formatDateOrderError.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  DevStoryRoute,
  ProjectRouteContainer,
  ProjectCyclesView,
  ProjectModulesView,
  DraftsWorkspaceView,
} from './routes';
import { saveDraft } from '../features/drafts/draftsStore';
import * as viewsApi from '../features/views/viewsApi';
import * as railApi from '../features/drawer-rail/railApi';
import * as clientModule from '../api/client';
import { ThemeProvider } from '../theme/ThemeProvider';

function wrapWithClient(ui: React.ReactElement, initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe('DevStoryRoute branches', () => {
  const devPaths = [
    { path: '/__dev/tokens', testId: 'token-story' },
    { path: '/__dev/emoji', testId: 'emoji-story' },
    { path: '/__dev/editor', testId: 'editor-story' },
    { path: '/__dev/media', testId: 'media-story' },
    { path: '/__dev/realtime', testId: 'realtime-story' },
    { path: '/__dev/drawer', testId: 'drawer-story' },
    { path: '/__dev/drawer-rail', testId: 'rail-story' },
    { path: '/__dev/rail', testId: 'rail-story' },
    { path: '/__dev/drawer-actions', testId: 'drawer-actions-story' },
    { path: '/__dev/stickies', testId: 'stickies-story' },
    { path: '/__dev/icons', testId: 'icon-story' },
  ];

  for (const { path, testId } of devPaths) {
    it(`renders component for path ${path}`, () => {
      const { unmount } = wrapWithClient(
        <Routes>
          <Route path="/__dev/*" element={<DevStoryRoute />} />
        </Routes>,
        [path],
      );
      expect(screen.getByTestId(testId)).toBeDefined();
      unmount();
    });
  }

  it('renders NotFoundView for unknown dev path', () => {
    wrapWithClient(
      <Routes>
        <Route path="/__dev/*" element={<DevStoryRoute />} />
      </Routes>,
      ['/__dev/non-existent-story'],
    );
    expect(screen.getByTestId('not-found-view')).toBeDefined();
  });
});

describe('ProjectRouteContainer guard branches', () => {
  it('renders NotFoundView when projectKey is invalid or contains undefined', () => {
    wrapWithClient(
      <Routes>
        <Route path="/projects/:projectKey/issues" element={<ProjectRouteContainer />} />
      </Routes>,
      ['/projects/--invalid/issues'],
    );
    expect(screen.getByTestId('not-found-view')).toBeDefined();
  });

  it('renders NotFoundView when issueKey regex fails', () => {
    wrapWithClient(
      <Routes>
        <Route path="/projects/:projectKey/issues/:issueKey" element={<ProjectRouteContainer />} />
      </Routes>,
      ['/projects/KAN/issues/not-a-valid-issue-key'],
    );
    expect(screen.getByTestId('not-found-view')).toBeDefined();
  });

  it('renders NotFoundView on 404 project response', async () => {
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue(new Response('Not Found', { status: 404 }));

    wrapWithClient(
      <Routes>
        <Route path="/projects/:projectKey/issues" element={<ProjectRouteContainer />} />
      </Routes>,
      ['/projects/NOTFOUND/issues'],
    );

    await waitFor(() => {
      expect(screen.getByTestId('not-found-view')).toBeDefined();
    });

    global.fetch = originalFetch;
  });

  it('handles server 500 error gracefully falling back to default capabilities', async () => {
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue(new Response('Server Error', { status: 500 }));

    wrapWithClient(
      <Routes>
        <Route element={<ProjectRouteContainer />}>
          <Route
            path="/projects/:projectKey/issues"
            element={<div data-testid="child-content">Project Outlet</div>}
          />
        </Route>
      </Routes>,
      ['/projects/KAN/issues'],
    );

    await waitFor(() => {
      expect(screen.queryByTestId('not-found-view')).toBeNull();
    });

    global.fetch = originalFetch;
  });
});

describe('ProjectCyclesView and ProjectModulesView status and date error branches', () => {
  it('renders all cycle status labels and handles date ordering validation error', async () => {
    const mockCycles = [
      { id: 'c-1', name: 'Cycle Progress', status: 'in_progress', start_date: '2026-11-01', end_date: '2026-11-15' },
      { id: 'c-2', name: 'Cycle Upcoming', status: 'upcoming', start_date: '2026-11-16', end_date: '2026-11-30' },
      { id: 'c-3', name: 'Cycle Planned', status: 'planned' },
      { id: 'c-4', name: 'Cycle Completed', status: 'completed' },
      { id: 'c-5', name: 'Cycle Backlog', status: 'backlog' },
      { id: 'c-6', name: 'Cycle Paused', status: 'paused' },
      { id: 'c-7', name: 'Cycle Cancelled', status: 'cancelled' },
      { id: 'c-8', name: 'Cycle Custom', status: 'custom_state' },
      { id: 'c-9', name: 'Cycle Empty', status: '' },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const p = path;
      if (p.includes('/cycles') && method === 'GET') {
        return Promise.resolve(mockCycles as never);
      }
      if (method === 'POST') {
        throw new Error('422 Unprocessable Entity: end date cannot be before start date');
      }
      return Promise.resolve({ success: true } as never);
    });

    wrapWithClient(
      <ProjectCyclesView capabilities={['ADMIN', 'EDIT']} />,
      ['/projects/KAN/cycles'],
    );

    await waitFor(() => {
      expect(screen.getByText('Cycle Progress')).toBeDefined();
    });

    // Check status badges
    expect(screen.getByText('In Progress')).toBeDefined();
    expect(screen.getByText('Planned')).toBeDefined();
    expect(screen.getByText('Completed')).toBeDefined();
    expect(screen.getByText('Backlog')).toBeDefined();
    expect(screen.getByText('Paused')).toBeDefined();
    expect(screen.getByText('Cancelled')).toBeDefined();
    expect(screen.getByText('Custom state')).toBeDefined();

    // Trigger date order error in create form
    const nameInput = screen.getByTestId('new-cycle-name-input');
    const startInput = screen.getByTestId('new-cycle-start-input');
    const endInput = screen.getByTestId('new-cycle-end-input');

    fireEvent.change(nameInput, { target: { value: 'Inverted Cycle' } });
    fireEvent.change(startInput, { target: { value: '2026-11-20' } });
    fireEvent.change(endInput, { target: { value: '2026-11-10' } });

    const submitBtn = screen.getByTestId('create-cycle-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('End date cannot be earlier than start date.')).toBeDefined();
    });
  });

  it('renders module status labels and handles target date order error', async () => {
    const mockModules = [
      { id: 'm-1', name: 'Module Alpha', status: 'in_progress' },
      { id: 'm-2', name: 'Module Beta', status: 'completed' },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const p = path;
      if (p.includes('/modules') && method === 'GET') {
        return Promise.resolve(mockModules as never);
      }
      if (method === 'POST') {
        throw new Error('422 target date validation failure');
      }
      return Promise.resolve({ success: true } as never);
    });

    wrapWithClient(
      <ProjectModulesView capabilities={['ADMIN', 'EDIT']} />,
      ['/projects/KAN/modules'],
    );

    await waitFor(() => {
      expect(screen.getByText('Module Alpha')).toBeDefined();
    });

    // Trigger target date error in create form
    const nameInput = screen.getByTestId('new-module-name-input');
    const startInput = screen.getByTestId('new-module-start-input');
    const targetInput = screen.getByTestId('new-module-target-input');

    fireEvent.change(nameInput, { target: { value: 'Inverted Module' } });
    fireEvent.change(startInput, { target: { value: '2026-11-20' } });
    fireEvent.change(targetInput, { target: { value: '2026-11-10' } });

    const submitBtn = screen.getByTestId('create-module-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Target date cannot be earlier than start date.')).toBeDefined();
    });
  });

  it('covers ProjectCyclesView edit with inverted dates, valid update, complete without target, and delete', async () => {
    const mockCycles = [
      { id: 'cyc-1', name: 'Sprint 1', status: 'in_progress', start_date: '2026-11-01', end_date: '2026-11-15' },
      { id: 'cyc-2', name: 'Sprint 2', status: 'backlog', start_date: null, end_date: null },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const p = path;
      if (p.includes('/cycles') && method === 'GET') {
        return Promise.resolve(mockCycles as never);
      }
      if (p.includes('/complete') && method === 'POST') {
        return Promise.resolve({ success: true } as never);
      }
      if (p.includes('/cycles/cyc-1') && method === 'PATCH') {
        return Promise.resolve({ id: 'cyc-1', name: 'Sprint 1 Updated' } as never);
      }
      return Promise.resolve({ success: true } as never);
    });

    wrapWithClient(
      <ProjectCyclesView capabilities={['ADMIN', 'EDIT', 'PROJECT_ADMIN']} />,
      ['/projects/KAN/cycles'],
    );

    await waitFor(() => {
      expect(screen.getByText('Sprint 1')).toBeDefined();
    });

    // 1. Invert edit dates
    fireEvent.click(screen.getByTestId('edit-cycle-btn-cyc-1'));
    fireEvent.change(screen.getByTestId('edit-cycle-start-input'), { target: { value: '2026-11-20' } });
    fireEvent.change(screen.getByTestId('edit-cycle-end-input'), { target: { value: '2026-11-10' } });
    fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

    await waitFor(() => {
      expect(screen.getByText('End date cannot be earlier than start date.')).toBeDefined();
    });

    // 2. Fix edit dates and save successfully
    fireEvent.change(screen.getByTestId('edit-cycle-end-input'), { target: { value: '2026-11-25' } });
    fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

    // 3. Complete without rollover target (empty string -> null)
    fireEvent.click(screen.getByTestId('complete-cycle-btn-cyc-1'));
    fireEvent.click(screen.getByTestId('confirm-complete-cycle-btn'));

    // 4. Delete cycle
    fireEvent.click(screen.getByTestId('delete-cycle-btn-cyc-2'));
  });

  it('covers ProjectModulesView edit with inverted dates, valid update, and delete', async () => {
    const mockModules = [
      { id: 'm-1', name: 'Module Alpha', status: 'in_progress', start_date: '2026-11-01', target_date: '2026-11-15' },
    ];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
      const p = path;
      if (p.includes('/modules') && method === 'GET') {
        return Promise.resolve(mockModules as never);
      }
      if (p.includes('/modules/m-1') && method === 'PATCH') {
        return Promise.resolve({ id: 'm-1', name: 'Module Alpha Updated' } as never);
      }
      return Promise.resolve({ success: true } as never);
    });

    wrapWithClient(
      <ProjectModulesView capabilities={['ADMIN', 'EDIT', 'PROJECT_ADMIN']} />,
      ['/projects/KAN/modules'],
    );

    await waitFor(() => {
      expect(screen.getByText('Module Alpha')).toBeDefined();
    });

    // Invert edit target date
    fireEvent.click(screen.getByTestId('edit-module-btn-m-1'));
    fireEvent.change(screen.getByTestId('edit-module-start-input'), { target: { value: '2026-11-20' } });
    fireEvent.change(screen.getByTestId('edit-module-target-input'), { target: { value: '2026-11-10' } });
    fireEvent.click(screen.getByTestId('save-edit-module-btn'));

    await waitFor(() => {
      expect(screen.getByText('Target date cannot be earlier than start date.')).toBeDefined();
    });

    // Fix date and save
    fireEvent.change(screen.getByTestId('edit-module-target-input'), { target: { value: '2026-11-25' } });
    fireEvent.click(screen.getByTestId('save-edit-module-btn'));

    // Delete module
    fireEvent.click(screen.getByTestId('delete-module-btn-m-1'));
  });

  it('publishes draft with live matching state_id and module_ids and handles fallbacks', async () => {
    saveDraft({
      id: 'draft-match-test',
      projectKey: 'KAN',
      summary: 'Draft with live state and module matching',
      prioritySlug: 'medium',
      stateId: 'uuid-state-1',
      moduleIds: ['mod-live-1', 'mod-missing'],
    });

    vi.spyOn(viewsApi, 'fetchProjectStates').mockResolvedValue([
      { id: 'uuid-state-1', name: 'In Progress', category: 'started' } as never,
    ]);
    vi.spyOn(railApi, 'fetchProjectModules').mockResolvedValue([
      { id: 'mod-live-1', name: 'Module 1', project_key: 'KAN' } as never,
    ]);

    const postSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ success: true });

    wrapWithClient(<DraftsWorkspaceView />, ['/workspaces/drafts']);

    await waitFor(() => {
      expect(screen.getByText('Draft with live state and module matching')).toBeDefined();
    });

    const publishBtn = screen.getByRole('button', { name: /Publish to Board/i });
    fireEvent.click(publishBtn);

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalled();
    });
  });
});
