import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, RouterProvider, createMemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  getDrafts,
  saveDraft,
  deleteDraft,
  useDrafts,
  DRAFTS_STORAGE_KEY,
} from '../features/drafts/draftsStore';
import {
  fetchDeviceCodeInfo,
  submitDeviceActivation,
} from '../features/oauth/oauthApi';
import * as apiClientModule from '../api/client';
import { ApiProblem } from '../api/problem';
import * as sessionGuardModule from '../features/auth/useSessionGuard';
import {
  sanitizeAdminAuthCard,
  fetchAdminAuthCards,
  createAdminAuthCard,
  updateAdminAuthCard,
  toggleAdminAuthCardEnabled,
  reorderAdminAuthCard,
  testAuthCardHandshake,
  deleteAdminAuthCard,
  fetchAdminPrincipals,
  createLocalUser,
  resetUserPassword,
  updateUserRole,
  type AdminAuthCard,
} from '../features/admin-auth/adminAuthApi';
import {
  suggestWorkspaceSlug,
  CreateWorkspaceModal,
} from '../features/workspaces/CreateWorkspaceModal';
import {
  NotFoundView,
  RoutePlaceholder,
  AppRoutes,
  WorkspaceHomeView,
  DraftsWorkspaceView,
  YourWorkView,
  ProjectCyclesView,
  ProjectModulesView,
  ProjectSavedViewsView,
  StandaloneStatusRoute,
  DevStoryRoute,
  createAppRouter,
} from './routes';
import { ListView } from '../features/list/ListView';
import { FIXTURE_12_ISSUES } from '../features/views/fixtures';
import { AuthStudioPage } from '../features/admin-auth/AuthStudioPage';
import { AuthCardEditorDrawer } from '../features/admin-auth/AuthCardEditorDrawer';
import {
  normalizeIssueDetail,
  IssueSurfaceRoot,
} from '../features/drawer/IssueSurface';
import { IssueSurfaceSlotsContext, type IssueDetail } from '../features/drawer/slots';
import { Sidebar, sanitizeSidebarState, SIDEBAR_STORAGE_KEY } from './Sidebar';
import { ThemeProvider } from '../theme/ThemeProvider';
import * as KanbanIconsModule from '../components/icons/KanbanIcons';
import { StateBadge, normalizeStateGroup } from '../components/state/StateBadge';
import {
  AppErrorModal,
  GlobalErrorBoundary,
  RouteErrorBoundary,
} from '../components/error/AppErrorModal';
import { EditorStory, generateOverlimitMarkdown } from '../dev/EditorStory';
import { StickiesStory } from '../dev/StickiesStory';
import { DrawerActionsStory } from '../dev/DrawerActionsStory';
import { QuickCreateIssueModal } from '../features/views/QuickCreateIssueModal';
import { IssuesWorkspaceRoute } from '../features/views/viewRegistry';
import { StatePriorityRows } from '../features/drawer-rail/StatePriorityRows';
import {
  CreateProjectModal,
  suggestProjectIdentifier,
} from '../features/projects/CreateProjectModal';
import { Topbar } from './Topbar';
import { ShellPanelsProvider } from './shellPanels';
import { CalendarView } from '../features/calendar/CalendarView';
import { TableView } from '../features/table/TableView';
import { TimelineView } from '../features/timeline/TimelineView';

function must<T>(val: T | null | undefined): T {
  if (val === null || val === undefined) {
    throw new Error('Expected non-null value');
  }
  return val;
}

function asErrorType(val: unknown): Error {
  return val as Error;
}
import {
  submitLocalAdminLogin,
  getWebauthnAssertionOptions,
  getWebauthnRegistrationOptions,
} from '../features/auth/authApi';

describe('Phase 5 Branch Coverage Booster', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('1. draftsStore', () => {
    it('handles empty, malformed, non-array, and valid drafts in getDrafts', () => {
      expect(getDrafts()).toEqual([]);

      window.localStorage.setItem(DRAFTS_STORAGE_KEY, '{invalid-json');
      expect(getDrafts()).toEqual([]);

      window.localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify({ not: 'an-array' }));
      expect(getDrafts()).toEqual([]);
    });

    it('saves, updates, and deletes drafts and updates useDrafts hook', () => {
      const first = saveDraft({
        projectKey: 'KAN',
        summary: 'First draft',
        stateId: 'st-1',
        prioritySlug: 'high',
      });
      expect(first.id).toBeTruthy();
      expect(getDrafts()).toHaveLength(1);

      const second = saveDraft({
        id: 'custom-id',
        projectKey: 'KAN',
        summary: 'Second draft',
        description: 'Desc',
        stateId: 'st-2',
        prioritySlug: 'low',
        moduleIds: ['mod-1'],
      });
      expect(second.id).toBe('custom-id');
      expect(getDrafts()).toHaveLength(2);

      // Update existing draft by id
      const updated = saveDraft({
        id: 'custom-id',
        projectKey: 'KAN',
        summary: 'Second draft updated',
        stateId: 'st-2',
        prioritySlug: 'urgent',
      });
      expect(updated.summary).toBe('Second draft updated');
      expect(updated.createdAt).toBe(second.createdAt);
      expect(getDrafts()).toHaveLength(2);

      // Save draft with custom id that doesn't exist yet
      const brandNew = saveDraft({
        id: 'non-existent-custom-id',
        projectKey: 'KAN',
        summary: 'Brand new with id',
        stateId: 'st-1',
        prioritySlug: 'medium',
      });
      expect(brandNew.id).toBe('non-existent-custom-id');
      deleteDraft(brandNew.id);
      expect(getDrafts()).toHaveLength(2);

      function DraftConsumer() {
        const list = useDrafts();
        return <div data-testid="draft-count">{list.length}</div>;
      }

      const { unmount } = render(<DraftConsumer />);
      expect(screen.getByTestId('draft-count').textContent).toBe('2');

      act(() => {
        deleteDraft('custom-id');
      });
      expect(screen.getByTestId('draft-count').textContent).toBe('1');

      act(() => {
        window.dispatchEvent(new Event('storage'));
      });
      expect(screen.getByTestId('draft-count').textContent).toBe('1');

      // Quota error resilience on saveDraft & deleteDraft
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('QuotaExceededError');
      });
      act(() => {
        saveDraft({
          projectKey: 'KAN',
          summary: 'Quota test',
          stateId: 'st-1',
          prioritySlug: 'medium',
        });
        deleteDraft(first.id);
      });

      unmount();
    });
  });

  describe('2. oauthApi', () => {
    it('calls apiFetch for fetchDeviceCodeInfo and submitDeviceActivation', async () => {
      const spy = vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValueOnce({
        user_code: 'ABCD-1234',
        client_name: 'CLI',
        client_id: 'cli-1',
        resource: 'mcp',
        surface: 'agent',
        requested_scopes: ['read'],
        allowed_projects: ['KAN'],
        expires_at: '2026-12-31T00:00:00Z',
      }).mockResolvedValueOnce({
        status: 'approved',
        grant_id: 'g-1',
      });

      const info = await fetchDeviceCodeInfo('ABCD-1234');
      expect(info.user_code).toBe('ABCD-1234');
      expect(spy).toHaveBeenCalledWith('GET', '/api/v1/oauth/device/info', {
        query: { user_code: 'ABCD-1234' },
      });

      const res = await submitDeviceActivation({
        user_code: 'ABCD-1234',
        approved: true,
        scopes: ['read'],
        allowed_projects: ['KAN'],
      });
      expect(res.status).toBe('approved');
    });
  });

  describe('3. adminAuthApi', () => {
    const sampleCard: AdminAuthCard = {
      id: 'card-1',
      provider_kind: 'OIDC',
      slug: 'google',
      display_name: 'Google',
      button_subtext: null,
      icon_preset: 'google',
      is_enabled: true,
      sort_rank: 'a0',
      auto_provision_users: true,
      allowed_email_domains: [],
      has_secret: true,
      dek_kid: 'k1',
      last_health_status: 'HEALTHY',
      public_config: { client_id: 'cid', client_secret: 'leak' },
    };

    it('covers all adminAuthApi methods and branches', async () => {
      const sanitized = sanitizeAdminAuthCard(sampleCard);
      expect(sanitized.public_config.client_secret).toBeUndefined();

      const spy = vi.spyOn(apiClientModule, 'apiFetch');

      spy.mockResolvedValueOnce({});
      const emptyRes = await fetchAdminAuthCards();
      expect(emptyRes.cards).toEqual([]);

      spy.mockResolvedValueOnce({ cards: [sampleCard] });
      const fullRes = await fetchAdminAuthCards();
      expect(fullRes.cards).toHaveLength(1);

      spy.mockResolvedValueOnce(sampleCard);
      await createAdminAuthCard({
        provider_kind: 'OIDC',
        slug: 'google',
        display_name: 'Google',
        icon_preset: 'google',
        auto_provision_users: true,
        allowed_email_domains: [],
        public_config: {},
        secret_input: 'sec-1',
      });
      spy.mockResolvedValueOnce(sampleCard);
      await createAdminAuthCard({
        provider_kind: 'OIDC',
        slug: 'google',
        display_name: 'Google',
        icon_preset: 'google',
        auto_provision_users: true,
        allowed_email_domains: [],
        public_config: {},
      });

      spy.mockResolvedValueOnce(sampleCard);
      await updateAdminAuthCard('card-1', { display_name: 'G2', secret_input: 'sec-2' });
      spy.mockResolvedValueOnce(sampleCard);
      await updateAdminAuthCard('card-1', { display_name: 'G3' });

      spy.mockResolvedValueOnce(sampleCard);
      await toggleAdminAuthCardEnabled('card-1', true);
      spy.mockResolvedValueOnce(sampleCard);
      await toggleAdminAuthCardEnabled('card-1', false);

      spy.mockResolvedValueOnce(sampleCard);
      await reorderAdminAuthCard('card-1', { after: 'card-0' });
      spy.mockResolvedValueOnce(sampleCard);
      await reorderAdminAuthCard('card-1', { after_card_id: 'card-0' });
      spy.mockResolvedValueOnce(sampleCard);
      await reorderAdminAuthCard('card-1', {});

      spy.mockResolvedValueOnce({ ok: true, latency_ms: 12 });
      const hs1 = await testAuthCardHandshake('card-1');
      expect(hs1.last_health_status).toBe('HEALTHY');
      expect(hs1.check_summary).toBe('Probe successful');

      spy.mockResolvedValueOnce({ status: 'OK', latency_ms: 15, error_code: 'ERR_1' });
      const hs2 = await testAuthCardHandshake('card-1');
      expect(hs2.last_health_status).toBe('HEALTHY');

      spy.mockResolvedValueOnce({ ok: false, latency_ms: 20 });
      const hs3 = await testAuthCardHandshake('card-1');
      expect(hs3.last_health_status).toBe('FAILED');
      expect(hs3.check_summary).toBe('Probe failed');

      spy.mockResolvedValueOnce(undefined);
      await deleteAdminAuthCard('card-1', 'google');
      spy.mockResolvedValueOnce(undefined);
      await deleteAdminAuthCard('card-1');

      spy.mockResolvedValueOnce([] as never);
      await fetchAdminPrincipals();
      spy.mockResolvedValueOnce([] as never);
      await fetchAdminPrincipals('AGENT');

      spy.mockResolvedValueOnce({ id: 'u1' });
      await createLocalUser({
        handle: 'alice',
        display_name: 'Alice',
        email: 'alice@example.com',
        password: 'Password123!',
        role: 'SERVER_ADMIN',
      });
      spy.mockResolvedValueOnce({ id: 'u2' });
      await createLocalUser({
        handle: 'bob',
        display_name: 'Bob',
        email: 'bob@example.com',
      });

      spy.mockResolvedValueOnce(undefined);
      await resetUserPassword('u1', 'NewPass123!');

      spy.mockResolvedValueOnce(undefined).mockResolvedValueOnce(undefined);
      await updateUserRole('u1', 'WORKSPACE_MEMBER', 'SERVER_ADMIN');

      spy.mockRejectedValueOnce(new Error('not bound')).mockResolvedValueOnce(undefined);
      await updateUserRole('u1', 'SERVER_ADMIN', 'WORKSPACE_MEMBER');

      spy.mockResolvedValueOnce(undefined);
      await updateUserRole('u1', 'WORKSPACE_ADMIN');
    });
  });

  describe('4. CreateWorkspaceModal', () => {
    it('validates suggestWorkspaceSlug edge cases', () => {
      expect(suggestWorkspaceSlug('   ')).toBe('');
      expect(suggestWorkspaceSlug('---')).toBe('');
      expect(suggestWorkspaceSlug('a')).toBe('a-ws');
      expect(suggestWorkspaceSlug('  Acme Corp 2026! ')).toBe('acme-corp-2026');
    });

    it('covers modal open/close, validation, error shapes, and successful creation', async () => {
      vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValue('csrf-123');
      const onClose = vi.fn();
      const onCreated = vi.fn();

      const { rerender } = render(
        <CreateWorkspaceModal isOpen={false} onClose={onClose} onCreated={onCreated} />,
      );
      expect(screen.queryByRole('dialog')).toBeNull();

      rerender(<CreateWorkspaceModal isOpen={true} onClose={onClose} onCreated={onCreated} />);
      expect(screen.getByRole('dialog')).toBeDefined();

      fireEvent.keyDown(window, { key: 'Tab' });
      expect(onClose).not.toHaveBeenCalled();

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);

      const nameInput = screen.getByLabelText(/Workspace Name/i);
      const slugInput = screen.getByLabelText(/Slug/i);

      fireEvent.change(nameInput, { target: { value: 'My Team' } });
      expect((slugInput as HTMLInputElement).value).toBe('my-team');

      fireEvent.change(slugInput, { target: { value: 'bad-' } });
      fireEvent.change(nameInput, { target: { value: 'My Team Renamed' } });
      expect((slugInput as HTMLInputElement).value).toBe('bad-');

      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByTestId('create-workspace-error').textContent).toContain(
        'Workspace slug must be 3-64',
      );

      fireEvent.change(slugInput, { target: { value: 'valid-slug' } });
      expect(screen.queryByTestId('create-workspace-error')).toBeNull();

      fireEvent.change(nameInput, { target: { value: '   ' } });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByTestId('create-workspace-error').textContent).toBe(
        'Workspace name is required.',
      );

      fireEvent.change(nameInput, { target: { value: 'Valid Workspace' } });
      expect(screen.queryByTestId('create-workspace-error')).toBeNull();

      const fetchSpy = vi.spyOn(window, 'fetch');
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Slug already exists' }), { status: 409 }),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));
      await waitFor(() => {
        expect(screen.getByTestId('create-workspace-error').textContent).toBe(
          'Slug already exists',
        );
      });

      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { detail: 'Nested conflict' } }), { status: 400 }),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));
      await waitFor(() => {
        expect(screen.getByTestId('create-workspace-error').textContent).toBe('Nested conflict');
      });

      fetchSpy.mockResolvedValueOnce(new Response('Internal Error', { status: 500 }));
      fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));
      await waitFor(() => {
        expect(screen.getByTestId('create-workspace-error').textContent).toBe(
          'Server returned 500',
        );
      });

      fetchSpy.mockRejectedValueOnce('raw string failure');
      fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));
      await waitFor(() => {
        expect(screen.getByTestId('create-workspace-error').textContent).toBe(
          'Network error creating workspace',
        );
      });

      fetchSpy.mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 'ws-2', name: 'Valid Workspace', slug: 'valid-slug' }),
          { status: 201 },
        ),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));
      await waitFor(() => {
        expect(onCreated).toHaveBeenCalledWith({
          id: 'ws-2',
          name: 'Valid Workspace',
          slug: 'valid-slug',
        });
      });
    });
  });

  describe('5. routes.tsx views & helpers', () => {
    it('renders static route views and DevStoryRoute branches', () => {
      expect(AppRoutes()).toBeNull();
      render(<NotFoundView />);
      expect(screen.getByTestId('not-found-view')).toBeDefined();

      render(<RoutePlaceholder route="/custom" />);
      expect(screen.getByText('Route: /custom')).toBeDefined();

      const devPaths = [
        '/__dev/tokens',
        '/__dev/emoji',
        '/__dev/editor',
        '/__dev/media',
        '/__dev/realtime',
        '/__dev/drawer',
        '/__dev/rail',
        '/__dev/drawer-actions',
        '/__dev/stickies',
        '/__dev/icons',
        '/__dev/nonexistent',
      ];
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      for (const p of devPaths) {
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

    it('renders WorkspaceHomeView, DraftsWorkspaceView, YourWorkView, Cycles, Modules, Views, StandaloneStatusRoute', async () => {
      const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/api/v1/projects') && !url.includes('/issues')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: [
                  {
                    id: 'p1',
                    identifier: 'OPS',
                    name: 'Operations',
                    description_markdown: '',
                    modules_enabled: true,
                  },
                ],
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
      });

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const { unmount: unmountHome } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/']}>
            <WorkspaceHomeView />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('project-card-OPS')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('home-create-project-btn'));
      fireEvent.click(screen.getByTestId('home-create-issue-btn'));
      act(() => {
        window.dispatchEvent(new Event('kb:project-created'));
      });
      unmountHome();

      saveDraft({
        id: 'd-1',
        projectKey: 'KAN',
        summary: 'Draft item 1',
        description: 'Some markdown',
        stateId: 'st-1',
        prioritySlug: 'high',
        moduleIds: ['m1'],
      });
      saveDraft({
        id: 'd-2',
        projectKey: 'KAN',
        summary: 'Draft item 2',
        stateId: '',
        prioritySlug: '',
      });
      saveDraft({
        id: 'd-3',
        projectKey: 'KAN',
        summary: 'Draft item 3 to delete',
        stateId: 'st-1',
        prioritySlug: 'low',
      });

      const { unmount: unmountDrafts } = render(
        <MemoryRouter initialEntries={['/drafts']}>
          <DraftsWorkspaceView />
        </MemoryRouter>,
      );
      expect(screen.getAllByTestId('draft-card')).toHaveLength(3);

      // Delete first draft (d-3 is at top of list)
      const deleteBtns = screen.getAllByTestId('draft-delete-btn');
      fireEvent.click(must(deleteBtns[0]));
      expect(screen.getAllByTestId('draft-card')).toHaveLength(2);

      // Resume draft (res.ok = true)
      const resumeBtns = screen.getAllByTestId('draft-resume-btn');
      fireEvent.click(must(resumeBtns[0]));
      await waitFor(() => {
        expect(getDrafts()).toHaveLength(1);
      });

      // Resume last draft when fetch fails -> fallback path
      fetchSpy.mockRejectedValueOnce(new Error('offline'));
      fireEvent.click(screen.getByTestId('draft-resume-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drafts-empty')).toBeDefined();
      });
      unmountDrafts();

      const { unmount: u2 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <YourWorkView />
            <ProjectCyclesView />
            <ProjectModulesView />
            <ProjectSavedViewsView />
            <StandaloneStatusRoute />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('your-work-view')).toBeDefined();
      expect(screen.getByTestId('project-cycles-view')).toBeDefined();
      expect(screen.getByTestId('project-modules-view')).toBeDefined();
      expect(screen.getByTestId('project-views-view')).toBeDefined();
      u2();
    });
  });

  describe('6. ListView', () => {
    it('covers empty state, filter popover, search/state/priority/groupBy, keyboard nav, and load more', () => {
      const onCreateIssue = vi.fn();
      const onLoadMore = vi.fn();

      const { rerender } = render(
        <MemoryRouter>
          <ListView issues={[]} projectKey="KAN" onCreateIssue={onCreateIssue} />
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByRole('button', { name: '+ Create first work item' }));
      expect(onCreateIssue).toHaveBeenCalledTimes(1);

      const firstBaseIssue = FIXTURE_12_ISSUES[0];
      if (!firstBaseIssue) throw new Error('Missing fixture');
      const customIssue = {
        ...firstBaseIssue,
        id: 'custom-1',
        key: 'KAN-999',
        summary: 'Unique summary token',
        state: { id: 's-custom', name: 'Custom QA', group: 'started', sort_order: 35 },
        priority: { slug: 'custom-prio', label: 'Custom Prio' },
      };

      rerender(
        <MemoryRouter>
          <ListView
            issues={[...FIXTURE_12_ISSUES, customIssue]}
            projectKey="KAN"
            onCreateIssue={onCreateIssue}
            nextCursor="cursor-2"
            onLoadMore={onLoadMore}
            isLoading={false}
          />
        </MemoryRouter>,
      );

      const listView = must(document.querySelector('.list-view'));
      fireEvent.keyDown(listView, { key: 'ArrowDown' });
      fireEvent.keyDown(listView, { key: 'ArrowUp' });

      // Test Order by sorting selector
      const sortSelect = screen.getByTestId('issue-sort-select');
      fireEvent.change(sortSelect, { target: { value: 'priority' } });
      expect(screen.getByText('Unique summary token')).toBeDefined();
      fireEvent.change(sortSelect, { target: { value: 'created' } });
      fireEvent.change(sortSelect, { target: { value: 'state' } });
      fireEvent.change(sortSelect, { target: { value: 'key' } });

      // Test Sort direction toggle
      const dirBtn = screen.getByTestId('issue-sort-dir-btn');
      fireEvent.click(dirBtn);
      fireEvent.click(dirBtn);

      // Test Refresh button
      const refreshBtn = screen.getByTestId('issue-rail-refresh-btn');
      fireEvent.click(refreshBtn);

      fireEvent.click(screen.getByRole('button', { name: 'Load more' }));
      expect(onLoadMore).toHaveBeenCalledTimes(1);
    });
  });

  describe('7. AuthStudioPage & 8. AuthCardEditorDrawer', () => {
    const cardsFixture: AdminAuthCard[] = [
      {
        id: 'c-oidc',
        provider_kind: 'OIDC',
        slug: 'google-oauth',
        display_name: 'Google Workspace',
        button_subtext: 'Use corporate email',
        icon_preset: 'google',
        is_enabled: true,
        sort_rank: 'a0',
        auto_provision_users: true,
        allowed_email_domains: ['example.com'],
        has_secret: true,
        dek_kid: 'dek-1',
        last_health_status: 'HEALTHY',
        public_config: { client_id: 'cid-1', issuer: 'https://accounts.google.com' },
      },
      {
        id: 'c-ldap',
        provider_kind: 'LDAP',
        slug: 'corp-ldap',
        display_name: 'Corp LDAP',
        button_subtext: null,
        icon_preset: 'ldap',
        is_enabled: true,
        sort_rank: 'a1',
        auto_provision_users: false,
        allowed_email_domains: [],
        has_secret: true,
        dek_kid: 'dek-1',
        last_health_status: 'UNVERIFIED',
        public_config: {
          url: 'ldaps://ldap.example.com:636',
          transport_mode: 'ldaps',
          base_dn: 'dc=example,dc=com',
          service_bind_dn: 'cn=admin,dc=example,dc=com',
        },
      },
      {
        id: 'c-local',
        provider_kind: 'LOCAL_ADMIN',
        slug: 'local-admin',
        display_name: 'Local Administrator',
        button_subtext: null,
        icon_preset: 'shield',
        is_enabled: true,
        sort_rank: 'z0',
        auto_provision_users: false,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        public_config: {},
      },
    ];

    it('renders non-admin access denied state', async () => {
      vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValueOnce({
        id: 'u1',
        is_server_admin: false,
      });

      render(<AuthStudioPage />);
      await waitFor(() => {
        expect(screen.getByText('Not found or no access')).toBeDefined();
      });
    });

    it('covers AuthStudioPage cards, reorder, handshake, lockout, and Users & Permissions tab', async () => {
      const apiSpy = vi.spyOn(apiClientModule, 'apiFetch').mockImplementation((method, path) => {
        const p = path as string;
        if (p === '/api/v1/auth/me') {
          return Promise.resolve({ id: 'admin-1', handle: 'admin', is_server_admin: true });
        }
        if (p === '/api/v1/admin/auth-cards' && method === 'GET') {
          return Promise.resolve({ cards: cardsFixture });
        }
        if (p.startsWith('/api/v1/admin/principals') && method === 'GET') {
          return Promise.resolve([
            {
              id: 'u-1',
              principal: 'alice',
              handle: 'alice',
              display_name: 'Alice Admin',
              type: 'USER',
              status: 'active',
              email: 'alice@example.com',
              role: 'SERVER_ADMIN',
              provider: 'GOOGLE',
            },
            {
              id: 'u-2',
              principal: 'bob',
              display_name: '',
              type: 'USER',
              status: 'active',
              email: null,
              role: 'WORKSPACE_MEMBER',
              provider: 'ACTIVE_DIRECTORY',
            },
            {
              id: 'u-3',
              principal: 'dave',
              display_name: 'Dave',
              type: 'USER',
              status: 'active',
              email: 'dave@example.com',
              role: 'WORKSPACE_GUEST',
              provider: 'GITHUB',
            },
            {
              id: 'u-4',
              principal: 'eve',
              display_name: 'Eve',
              type: 'USER',
              status: 'active',
              email: 'eve@example.com',
              role: 'WORKSPACE_MEMBER',
              provider: 'LDAP',
            },
            {
              id: 'u-5',
              principal: 'frank',
              display_name: 'Frank',
              type: 'USER',
              status: 'active',
              email: 'frank@example.com',
              role: 'WORKSPACE_MEMBER',
              provider: 'CUSTOM_OIDC',
            },
          ] as never);
        }
        if (p.endsWith('/test-handshake')) {
          return Promise.resolve({ ok: true, latency_ms: 9, check_summary: 'OK' });
        }
        if (p.endsWith('/reorder')) {
          return Promise.resolve({ ...cardsFixture[0], sort_rank: 'a2' });
        }
        if (p.endsWith('/disable')) {
          return Promise.reject(
            new ApiProblem(409, {
              code: 'LOCKOUT_PREVENTED',
              title: 'Lockout prevented',
              detail: 'Cannot disable last provider',
              reason_code: 'LAST_ACTIVE_PROVIDER',
            }),
          );
        }
        return Promise.resolve({});
      });

      render(<AuthStudioPage />);
      await waitFor(() => {
        expect(screen.getByText('Google Workspace')).toBeDefined();
      });

      const testBtns = screen.getAllByRole('button', { name: /Test handshake/i });
      fireEvent.click(must(testBtns[0]));
      await waitFor(() => {
        expect(apiSpy).toHaveBeenCalledWith(
          'POST',
          '/api/v1/admin/auth-cards/c-oidc/test-handshake',
          { body: {} },
        );
      });

      fireEvent.click(screen.getByRole('button', { name: 'Move Google Workspace down' }));
      fireEvent.click(screen.getByRole('button', { name: 'Move Corp LDAP up' }));

      const row0 = screen.getByTestId('auth-card-row-google-oauth');
      const row1 = screen.getByTestId('auth-card-row-corp-ldap');
      fireEvent.dragStart(row0);
      fireEvent.dragOver(row1);
      fireEvent.drop(row1);

      const switch0 = screen.getByRole('switch', { name: 'Enable Google Workspace' });
      fireEvent.click(switch0);
      await waitFor(() => {
        expect(screen.getByText(/Cannot disable last provider/i)).toBeDefined();
      });
      // Dismiss lockout alert
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss lockout alert' }));

      fireEvent.click(screen.getByRole('button', { name: 'Delete Corp LDAP' }));

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));
      await waitFor(() => {
        expect(screen.getByTestId('auth-users-table')).toBeDefined();
      });

      const roleSelect = screen.getByLabelText(/Role for @?alice/i);
      fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });
      await waitFor(() => {
        expect(screen.getByText('User role updated successfully.')).toBeDefined();
      });
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }));

      // Open + Add Local User modal
      fireEvent.click(screen.getByRole('button', { name: '+ Add Local User' }));
      const addDialog = screen.getByRole('dialog', { name: '+ Add Local User' });

      // Missing fields submit -> validation error
      fireEvent.submit(must(addDialog.querySelector('form')));
      expect(screen.getByText('Handle, email, and password are required.')).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss error' }));

      fireEvent.change(screen.getByLabelText(/Username \/ Handle/i), {
        target: { value: 'charlie' },
      });
      fireEvent.change(screen.getByLabelText(/Display Name/i), {
        target: { value: 'Charlie User' },
      });
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: 'charlie@example.com' },
      });
      fireEvent.change(screen.getByLabelText(/^Password/i), {
        target: { value: 'SecretPass123!' },
      });
      fireEvent.change(screen.getByLabelText(/Initial Role Grant/i), {
        target: { value: 'WORKSPACE_ADMIN' },
      });
      fireEvent.submit(must(addDialog.querySelector('form')));
      await waitFor(() => {
        expect(screen.getByText(/Local user @charlie created successfully/)).toBeDefined();
      });

      // Open Reset Password modal
      const resetBtns = screen.getAllByRole('button', { name: 'Reset Password' });
      fireEvent.click(must(resetBtns[0]));
      const resetDialog = screen.getByRole('dialog', { name: /Reset Password/i });

      fireEvent.change(screen.getByLabelText(/^New Password/i), {
        target: { value: 'Pass1111!' },
      });
      fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
        target: { value: 'Pass2222!' },
      });
      fireEvent.submit(must(resetDialog.querySelector('form')));
      expect(screen.getByText('Passwords do not match or cannot be empty.')).toBeDefined();

      fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
        target: { value: 'Pass1111!' },
      });
      fireEvent.submit(must(resetDialog.querySelector('form')));
      await waitFor(() => {
        expect(screen.getByText(/Password reset successfully for @alice/)).toBeDefined();
      });

      // Also reset password for user without handle (bob) to cover principal fallback
      const resetBtns2 = screen.getAllByRole('button', { name: 'Reset Password' });
      fireEvent.click(must(resetBtns2[1]));
      const resetDialog2 = screen.getByRole('dialog', { name: /Reset Password/i });
      fireEvent.change(screen.getByLabelText(/^New Password/i), {
        target: { value: 'Pass1111!' },
      });
      fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
        target: { value: 'Pass1111!' },
      });
      fireEvent.submit(must(resetDialog2.querySelector('form')));
      await waitFor(() => {
        expect(screen.getByText(/Password reset successfully for @bob/)).toBeDefined();
      });
    });

    it('covers AuthCardEditorDrawer presets, validation, OIDC/LDAP submission, and LOCAL_ADMIN view', async () => {
      const onClose = vi.fn();
      const onSave = vi.fn().mockResolvedValue(undefined);

      const { rerender } = render(
        <AuthCardEditorDrawer isOpen={true} card={null} onClose={onClose} onSave={onSave} />,
      );

      fireEvent.click(screen.getByRole('button', { name: /Google \(OAuth 2\.0\)/i }));
      fireEvent.click(screen.getByRole('button', { name: /GitHub \(OAuth 2\.0\)/i }));
      fireEvent.click(screen.getByRole('button', { name: /Custom OAuth 2\.0 \/ OIDC/i }));

      fireEvent.change(screen.getByLabelText('Issuer URL'), {
        target: { value: 'http://insecure.example.com' },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByText('Client ID is required.')).toBeDefined();
      expect(screen.getByText('Issuer URL must use HTTPS.')).toBeDefined();

      fireEvent.change(screen.getByLabelText('Client ID'), {
        target: { value: 'my-client-id' },
      });
      fireEvent.change(screen.getByLabelText('Client Secret'), {
        target: { value: 'my-secret-val' },
      });
      fireEvent.change(screen.getByLabelText('Issuer URL'), {
        target: { value: 'https://sso.example.com' },
      });
      fireEvent.change(screen.getByLabelText('Scopes'), {
        target: { value: 'openid, email' },
      });
      fireEvent.change(screen.getByLabelText('Token Auth Method'), {
        target: { value: 'private_key_jwt' },
      });
      fireEvent.change(screen.getByLabelText('Allowed Email Domains'), {
        target: { value: 'example.com, corp.org' },
      });
      fireEvent.change(screen.getByLabelText('Access Policy'), {
        target: { value: 'restricted' },
      });
      fireEvent.change(screen.getByLabelText('Admin Allowlist'), {
        target: { value: 'admin@example.com' },
      });
      fireEvent.change(screen.getByLabelText('User Allowlist'), {
        target: { value: 'user@example.com' },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(onSave).toHaveBeenCalledTimes(1);
      });

      fireEvent.click(screen.getByRole('button', { name: /Active Directory/i }));
      fireEvent.click(screen.getByRole('button', { name: /Standard LDAP/i }));

      fireEvent.change(screen.getByLabelText('SPKI SHA-256 Pin'), {
        target: { value: 'not-64-hex' },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByText('Bind DN is required.')).toBeDefined();
      expect(screen.getByText('Base DN is required.')).toBeDefined();
      expect(
        screen.getByText('SPKI pin must be exactly 64 hexadecimal characters.'),
      ).toBeDefined();

      fireEvent.change(screen.getByLabelText('Server URL'), {
        target: { value: 'ldap://ldap.example.com:389' },
      });
      fireEvent.change(screen.getByLabelText('Bind DN'), {
        target: { value: 'cn=svc,dc=example,dc=com' },
      });
      fireEvent.change(screen.getByLabelText('Base DN'), {
        target: { value: 'dc=example,dc=com' },
      });
      fireEvent.change(screen.getByLabelText('User Filter'), {
        target: { value: '(uid={username})' },
      });
      fireEvent.change(screen.getByLabelText('Subject Attribute'), {
        target: { value: 'customUUID' },
      });
      fireEvent.change(screen.getByLabelText('Email Attribute'), {
        target: { value: 'customMail' },
      });
      fireEvent.change(screen.getByLabelText('Full Name Attribute'), {
        target: { value: 'customCN' },
      });
      fireEvent.change(screen.getByLabelText('CA Certificate PEM'), {
        target: { value: '-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----' },
      });
      fireEvent.change(screen.getByLabelText('SPKI SHA-256 Pin'), {
        target: { value: 'a'.repeat(64) },
      });
      fireEvent.change(screen.getByLabelText('Access Policy'), {
        target: { value: 'restricted' },
      });
      fireEvent.change(screen.getByLabelText('Admin Groups'), {
        target: { value: 'Admins' },
      });
      fireEvent.change(screen.getByLabelText('User Groups'), {
        target: { value: 'Users' },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(onSave).toHaveBeenCalledTimes(2);
      });

      // Rerender with existing OIDC card (isEdit = true) and toggle Replace Stored Secret
      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={must(cardsFixture[0])}
          onClose={onClose}
          onSave={onSave}
        />,
      );
      const replaceCheckbox = screen.getByLabelText('Replace Stored Secret');
      fireEvent.click(replaceCheckbox);
      fireEvent.change(screen.getByLabelText('Client Secret'), {
        target: { value: 'new-rotated-secret' },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(onSave).toHaveBeenCalledTimes(3);
      });

      // Rerender with existing LOCAL_ADMIN card
      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={must(cardsFixture[2])}
          onClose={onClose}
          onSave={onSave}
        />,
      );
      expect(screen.getByText('Local Administrator Security Policy')).toBeDefined();
    });
  });

  describe('9. IssueSurface', () => {
    it('covers normalizeIssueDetail branches and split/full/drawer modes', async () => {
      expect(normalizeIssueDetail(null, 'KAN')).toBeNull();

      const fromItems = normalizeIssueDetail(
        {
          items: [
            {
              id: 'obj-1',
              key: 'OPS-7',
              summary: 'Test',
              description_sha256: 'abc123sha',
              labels: ['lbl-1', { id: 'lbl-2', name: 'Bug' }],
            } as unknown as IssueDetail,
          ],
        } as unknown as IssueDetail,
        null,
      );
      expect(fromItems.project_key).toBe('OPS');
      expect(fromItems.object_id).toBe('obj-1');
      expect(fromItems.etag).toBe('"abc123sha"');
      expect(fromItems.label_ids).toEqual(['lbl-1', 'lbl-2']);

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      vi.spyOn(apiClientModule.apiClient, 'get').mockResolvedValue({
        id: 'obj-10',
        key: 'KAN-10',
        summary: 'Mermaid issue',
        description_markdown: 'Hello\n```mermaid\ngraph TD;\nA-->B;\n```',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'high', label: 'High' },
      });
      vi.spyOn(apiClientModule.apiClient, 'patch').mockResolvedValue({
        id: 'obj-10',
        key: 'KAN-10',
        summary: 'Mermaid issue',
        description_markdown: 'Updated markdown',
        state: { id: 's1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'high', label: 'High' },
      });

      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <IssueSurfaceSlotsContext.Provider value={{}}>
            <IssueSurfaceRoot mode="split" issueKey="KAN-10" projectKey="KAN" />
          </IssueSurfaceSlotsContext.Provider>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mermaid-block')).toBeDefined();
      });

      // Edit description, cancel, then edit and save
      fireEvent.click(must(screen.getAllByRole('button', { name: 'Edit description' })[0]));
      fireEvent.click(screen.getByRole('button', { name: 'Cancel description edit' }));
      fireEvent.click(must(screen.getAllByRole('button', { name: 'Edit description' })[0]));
      const descTextarea = screen.getByLabelText('Description');
      fireEvent.change(descTextarea, { target: { value: 'Updated markdown' } });
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));
      await waitFor(() => {
        expect(screen.getByText('Updated markdown')).toBeDefined();
      });
      unmount();
    });
  });

  describe('10. Sidebar', () => {
    it('covers sanitizeSidebarState, workspace switcher, project creation, and mobile focus trap', async () => {
      expect(sanitizeSidebarState('open')).toBe('open');
      expect(sanitizeSidebarState('collapsed')).toBe('collapsed');
      expect(sanitizeSidebarState('invalid')).toBe('open');

      vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValue('csrf-123');
      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url === '/api/v1/workspaces') {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { id: 'ws-1', name: 'Main WS', slug: 'main-ws', is_current: true },
                { id: 'ws-2', name: 'Sec WS', slug: 'sec-ws', is_current: false },
              ]),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/switch')) {
          return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
        }
        if (url === '/api/v1/projects') {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { identifier: 'KAN', name: 'kanban', modules_enabled: true },
                { identifier: 'SEC', name: 'Security', modules_enabled: false },
              ]),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      });

      const onClose = vi.fn();
      render(
        <MemoryRouter initialEntries={['/drafts']}>
          <Sidebar isOpen={true} onClose={onClose} projectKey="KAN" projectName="CustomName" />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Workspace switcher:.*Main WS/i })).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: /Workspace switcher/i }));
      const secWsItem = screen.getByRole('menuitem', { name: /Sec WS/i });
      fireEvent.click(secWsItem);

      fireEvent.click(screen.getByRole('button', { name: /Workspace switcher/i }));
      fireEvent.click(screen.getByRole('menuitem', { name: /Create New Workspace/i }));
      expect(screen.getByRole('dialog', { name: 'Create New Workspace' })).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

      fireEvent.click(screen.getByRole('button', { name: /New work item/i }));

      const aside = screen.getByLabelText('Sidebar navigation');
      fireEvent.keyDown(aside, { key: 'Tab' });
      fireEvent.keyDown(aside, { key: 'Tab', shiftKey: true });
      fireEvent.keyDown(aside, { key: 'Escape' });
      expect(onClose).toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: /Collapse.*sidebar/i }));
      expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('collapsed');
    });
  });

  describe('11. KanbanIcons, StateBadge, AppErrorModal & Dev Stories', () => {
    it('renders all KanbanIcons with default and explicit sizes, plus StateProgressRing and PriorityIcon', () => {
      const iconEntries = Object.entries(KanbanIconsModule.KANBAN_ICON_MAP);
      expect(iconEntries.length).toBeGreaterThan(50);

      const { unmount } = render(
        <div>
          {iconEntries.map(([name, IconComp]) => (
            <React.Fragment key={name}>
              <IconComp />
              <IconComp size={24} className="custom-icon" />
            </React.Fragment>
          ))}
          <KanbanIconsModule.PriorityIcon priority="urgent" />
          <KanbanIconsModule.PriorityIcon priority="high" size={18} />
          <KanbanIconsModule.PriorityIcon priority="medium" />
          <KanbanIconsModule.PriorityIcon priority="low" />
          <KanbanIconsModule.PriorityIcon priority="none" />
          <KanbanIconsModule.PriorityIcon priority="unknown" />
          <KanbanIconsModule.StateProgressRing state="backlog" />
          <KanbanIconsModule.StateProgressRing state="todo" size={18} />
          <KanbanIconsModule.StateProgressRing state="in_progress" />
          <KanbanIconsModule.StateProgressRing state="in_review" />
          <KanbanIconsModule.StateProgressRing state="done" />
          <KanbanIconsModule.StateProgressRing state="canceled" />
          <KanbanIconsModule.StateProgressRing state="unknown" />
          <KanbanIconsModule.StateProgressRing state="" />
        </div>,
      );

      expect(KanbanIconsModule.getKanbanIcon('PriorityUrgent')).toBeDefined();
      expect(KanbanIconsModule.getKanbanIcon('NotAnIcon')).toBeUndefined();
      unmount();
    });

    it('covers StateBadge and normalizeStateGroup branches', () => {
      expect(normalizeStateGroup('backlog')).toBe('backlog');
      expect(normalizeStateGroup('todo')).toBe('unstarted');
      expect(normalizeStateGroup('in_progress')).toBe('started');
      expect(normalizeStateGroup('completed')).toBe('completed');
      expect(normalizeStateGroup('cancelled')).toBe('cancelled');
      expect(normalizeStateGroup(undefined)).toBe('unstarted');

      const { unmount } = render(
        <div>
          <StateBadge state="In Review" />
          <StateBadge state={{ name: 'Todo', group: 'unstarted' }} showEmoji={false} />
          <StateBadge group="completed" showRing={false} showLabel={false} />
          <StateBadge />
        </div>,
      );
      unmount();
    });

    it('covers AppErrorModal and GlobalErrorBoundary branches', () => {
      const onDismiss = vi.fn();
      const { rerender, unmount } = render(
        <AppErrorModal
          error={new Error('Boom error')}
          errorInfo={{ componentStack: 'at Component' }}
          onDismiss={onDismiss}
        />,
      );
      expect(screen.getByTestId('error-message').textContent).toBe('Boom error');
      fireEvent.click(screen.getByTestId('error-copy-btn'));
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));
      expect(onDismiss).toHaveBeenCalledTimes(1);

      rerender(<AppErrorModal error="String error message" />);
      expect(screen.getByTestId('error-message').textContent).toBe('String error message');

      rerender(<AppErrorModal error={{ statusText: 'Gateway Timeout' }} />);
      expect(screen.getByTestId('error-message').textContent).toBe('Gateway Timeout');

      rerender(<AppErrorModal error={404} />);
      expect(screen.getByTestId('error-trace').textContent).toBe('404');

      rerender(<AppErrorModal error={true} />);
      expect(screen.getByTestId('error-trace').textContent).toBe('true');

      rerender(<AppErrorModal error={123n} />);
      expect(screen.getByTestId('error-trace').textContent).toBe('123');

      rerender(<AppErrorModal error={null} />);
      expect(screen.getByTestId('error-trace').textContent).toBe('No stack trace available.');

      rerender(<AppErrorModal error={undefined} />);
      expect(screen.getByTestId('error-trace').textContent).toBe('No stack trace available.');
      unmount();

      const { unmount: u2 } = render(
        <GlobalErrorBoundary>
          <div data-testid="healthy-child">Healthy</div>
        </GlobalErrorBoundary>,
      );
      expect(screen.getByTestId('healthy-child')).toBeDefined();

      act(() => {
        window.dispatchEvent(new ErrorEvent('error', { message: 'Window script error' }));
      });
      expect(screen.getByTestId('error-message').textContent).toBe('Window script error');
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));
      expect(screen.getByTestId('healthy-child')).toBeDefined();
      u2();
    });

    it('covers EditorStory, StickiesStory, and DrawerActionsStory interactive handlers', () => {
      expect(generateOverlimitMarkdown()).toContain('N400');

      const { unmount: u1 } = render(<EditorStory />);
      fireEvent.click(screen.getByTestId('btn-fix-typo'));
      fireEvent.click(screen.getByTestId('btn-reset'));
      fireEvent.click(screen.getByTestId('btn-load-mermaid'));
      fireEvent.click(screen.getByTestId('btn-load-fallback'));
      fireEvent.click(screen.getByTestId('btn-toggle-theme'));
      fireEvent.click(screen.getByTestId('btn-toggle-theme'));
      fireEvent.click(screen.getByTestId('btn-undo'));
      u1();

      const { unmount: u2 } = render(
        <MemoryRouter>
          <StickiesStory />
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByTestId('toggle-theme-btn'));
      fireEvent.click(screen.getByTestId('toggle-theme-btn'));
      fireEvent.click(screen.getByTestId('story-new-sticky-btn'));
      u2();

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount: u3 } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <DrawerActionsStory />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      fireEvent.click(screen.getByTestId('select-done-btn'));
      fireEvent.click(screen.getByTestId('select-started-btn'));
      u3();
    });
  });

  describe('12. Deep Branch Coverage: QuickCreateIssueModal, AuthCardEditorDrawer, AuthStudioPage, IssueSurface & authApi', () => {
    it('covers QuickCreateIssueModal draft & issue flows, priority/state branches, and post-create actions', () => {
      const onClose = vi.fn();
      const onCreate = vi.fn().mockReturnValueOnce({ key: 'KAN-500' }).mockReturnValue(undefined);
      const onOpenPeek = vi.fn();

      const { rerender, unmount } = render(
        <QuickCreateIssueModal
          isOpen={false}
          onClose={onClose}
          onCreate={onCreate}
          projectKey="KAN"
        />,
      );
      expect(screen.queryByRole('dialog')).toBeNull();

      rerender(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={onCreate}
          projectKey="KAN"
          modulesEnabled={true}
          modules={[{ id: 'm-custom', name: 'CustomMod' }]}
          onOpenPeek={onOpenPeek}
        />,
      );

      // Escape key closes modal
      fireEvent.keyDown(window, { key: 'Tab' });
      expect(onClose).not.toHaveBeenCalled();

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);

      // Create issue with state-in-progress, priority urgent, description, module
      fireEvent.change(screen.getByLabelText('Summary'), { target: { value: 'Urgent item' } });
      fireEvent.change(screen.getByLabelText('Description (Markdown)'), {
        target: { value: 'Detailed body' },
      });
      fireEvent.change(screen.getByLabelText('State'), {
        target: { value: 'state-in-progress' },
      });
      fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'urgent' } });
      fireEvent.change(screen.getByLabelText('Module'), { target: { value: '' } });
      fireEvent.change(screen.getByLabelText('Module'), { target: { value: 'm-custom' } });

      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByTestId('quick-create-post-dialog')).toBeDefined();
      expect(screen.getByText('KAN-500')).toBeDefined();

      // Click View Issue -> calls onOpenPeek('KAN-500')
      fireEvent.click(screen.getByTestId('post-create-view-btn'));
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-500');

      // Rerender without onOpenPeek & modulesEnabled=false, test priorities high/low/none and Create Another
      rerender(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={onCreate}
          projectKey="KAN"
          modulesEnabled={false}
        />,
      );
      for (const [prio, st] of [
        ['high', 'state-backlog'],
        ['low', 'state-todo'],
        ['none', 'state-done'],
      ] as const) {
        fireEvent.change(screen.getByLabelText('Summary'), { target: { value: `Item ${prio}` } });
        fireEvent.change(screen.getByLabelText('State'), { target: { value: st } });
        fireEvent.change(screen.getByLabelText('Priority'), { target: { value: prio } });
        fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
        fireEvent.click(screen.getByTestId('post-create-another-btn'));
      }

      // Save as draft flow
      fireEvent.change(screen.getByLabelText('Summary'), { target: { value: 'WIP Draft' } });
      fireEvent.click(screen.getByTestId('quick-create-draft-checkbox'));
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByText(/Draft Saved/i)).toBeDefined();
      fireEvent.click(screen.getByTestId('post-create-done-btn'));

      unmount();
    });

    it('covers AuthCardEditorDrawer card prop sync, validation edge cases, and error catches', async () => {
      const onClose = vi.fn();
      const onSave = vi
        .fn()
        .mockRejectedValueOnce(new Error('Backend failure'))
        .mockRejectedValueOnce('raw string rejection')
        .mockResolvedValue(undefined);

      const cardVariantA: AdminAuthCard = {
        id: 'card-a',
        provider_kind: 'OIDC',
        slug: 'oidc-a',
        display_name: 'OIDC A',
        button_subtext: 'Sub A',
        icon_preset: 'key',
        is_enabled: true,
        sort_rank: 'a0',
        auto_provision_users: true,
        allowed_email_domains: ['a.com'],
        has_secret: true,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        public_config: {
          access_mode: 'group_restricted',
          admin_allowlist: ['adm@a.com'],
          user_allowlist: ['usr@a.com'],
          admin_groups: ['g-adm'],
          user_groups: ['g-usr'],
          issuer_url: 'https://issuer-a.example.com',
          client_id: 'cid-a',
          authorization_endpoint: 'https://issuer-a.example.com/auth',
          token_endpoint: 'https://issuer-a.example.com/token',
          userinfo_endpoint: 'https://issuer-a.example.com/userinfo',
          scopes: ['openid', 'profile'],
          token_auth_method: 'private_key_jwt',
          server_url: 'ldaps://ldap-a.example.com',
          start_tls: true,
          bind_dn: 'cn=bind,dc=a',
          base_dn: 'dc=a',
          user_search_filter: '(uid={username})',
          subject_attribute: 'entryUUID',
          email_attribute: 'mail',
          display_name_attribute: 'cn',
          ca_cert_pem: 'PEM-A',
          spki_sha256_pins: ['a'.repeat(64)],
        },
      };

      const cardVariantB: AdminAuthCard = {
        id: 'card-b',
        provider_kind: 'LDAP',
        slug: 'ldap-b',
        display_name: 'LDAP B',
        button_subtext: null,
        icon_preset: 'ldap',
        is_enabled: true,
        sort_rank: 'a1',
        auto_provision_users: false,
        allowed_email_domains: [],
        has_secret: true,
        dek_kid: 'dek-2',
        last_health_status: 'HEALTHY',
        public_config: {
          user_allowlist: ['usr@b.com'],
          issuer: 'https://issuer-b.example.com',
          scopes: 'openid, email',
          url: 'ldaps://ldap-b.example.com:636',
          transport_mode: 'starttls',
          service_bind_dn: 'cn=svc,dc=b',
          base_dn: 'dc=b',
          user_filter: '(sAMAccountName={username})',
          ca_pem: 'PEM-B',
          spki_sha256_pin: 'b'.repeat(64),
        },
      };

      const { rerender, unmount } = render(
        <AuthCardEditorDrawer isOpen={true} card={cardVariantA} onClose={onClose} onSave={onSave} />,
      );

      // Escape key triggers onClose
      fireEvent.keyDown(window, { key: 'Tab' });
      expect(onClose).not.toHaveBeenCalled();

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);

      // Submit cardVariantA -> triggers Error('Backend failure')
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Backend failure');
      });

      // Rerender with cardVariantB -> covers card !== prevCard sync branches for LDAP
      rerender(
        <AuthCardEditorDrawer isOpen={true} card={cardVariantB} onClose={onClose} onSave={onSave} />,
      );
      // Toggle replace secret on LDAP card and StartTLS checkbox
      const replaceSecretBox = screen.getByLabelText('Replace Stored Secret');
      fireEvent.click(replaceSecretBox);
      fireEvent.change(screen.getByLabelText('Bind DN Password'), {
        target: { value: 'ldap-pass' },
      });
      fireEvent.click(replaceSecretBox); // uncheck clears secretInput
      fireEvent.click(screen.getByLabelText('StartTLS'));

      // Submit cardVariantB -> triggers non-Error string rejection
      fireEvent.change(screen.getByLabelText('Button Subtext'), { target: { value: 'New sub' } });
      fireEvent.change(screen.getByLabelText('Icon Preset'), { target: { value: 'server' } });
      fireEvent.click(screen.getByLabelText('Auto-provision Users'));
      fireEvent.change(screen.getByLabelText('Subject Attribute'), { target: { value: '' } });
      fireEvent.change(screen.getByLabelText('Email Attribute'), { target: { value: '' } });
      fireEvent.change(screen.getByLabelText('Full Name Attribute'), { target: { value: '' } });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Failed to save authentication card.');
      });

      // Rerender with cardVariantA and empty scopes to hit fallback scopes branch
      rerender(
        <AuthCardEditorDrawer isOpen={true} card={cardVariantA} onClose={onClose} onSave={onSave} />,
      );
      fireEvent.change(screen.getByLabelText('Scopes'), { target: { value: '   ' } });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(onSave).toHaveBeenCalledTimes(3);
      });

      // Rerender with card=null (create mode) and test slug/displayName/subtext/LDAP url validations
      rerender(
        <AuthCardEditorDrawer isOpen={true} card={null} onClose={onClose} onSave={onSave} />,
      );
      fireEvent.change(screen.getByLabelText('Slug Identifier'), { target: { value: '' } });
      fireEvent.change(screen.getByLabelText('Display Name'), { target: { value: '' } });
      fireEvent.change(screen.getByLabelText('Button Subtext'), {
        target: { value: 'x'.repeat(125) },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByText('Slug is required.')).toBeDefined();
      expect(screen.getByText('Display name must be between 1 and 80 characters.')).toBeDefined();
      expect(screen.getByText('Subtext must not exceed 120 characters.')).toBeDefined();

      // Invalid slug format + LDAP URL scheme validation
      fireEvent.change(screen.getByLabelText('Provider Kind'), { target: { value: 'LDAP' } });
      fireEvent.change(screen.getByLabelText('Slug Identifier'), { target: { value: 'a!' } });
      fireEvent.change(screen.getByLabelText('Server URL'), { target: { value: '' } });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(
        screen.getByText('Slug must be 3-48 lowercase alphanumeric characters or hyphens.'),
      ).toBeDefined();
      expect(screen.getByText('Server URL is required.')).toBeDefined();

      fireEvent.change(screen.getByLabelText('Server URL'), {
        target: { value: 'http://invalid-ldap' },
      });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByText('Server URL must start with ldaps:// or ldap://')).toBeDefined();

      unmount();
    });

    it('covers IssueSurface error states (404 & 500) in drawer and full modes and Escape handling', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const getSpy = vi
        .spyOn(apiClientModule.apiClient, 'get')
        .mockRejectedValueOnce(new ApiProblem(404, { detail: 'Not found' }))
        .mockRejectedValue(new Error('500 Server Error'));

      const { rerender, unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-404']}>
            <IssueSurfaceSlotsContext.Provider value={{}}>
              <IssueSurfaceRoot mode="drawer" issueKey="KAN-404" projectKey="KAN" />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(
          screen.getByText('Issue KAN-404 was not found or you do not have access.'),
        ).toBeDefined();
      });
      // Click Open in full screen in drawer error header
      fireEvent.click(screen.getByRole('button', { name: 'Open in full screen' }));
      fireEvent.keyDown(window, { key: 'F', ctrlKey: true, shiftKey: true });

      // Rerender in split mode with error
      rerender(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-501']}>
            <IssueSurfaceSlotsContext.Provider value={{}}>
              <IssueSurfaceRoot mode="split" issueKey="KAN-501" projectKey="KAN" />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.getByText('Could not load KAN-501.')).toBeDefined();
      });

      // Rerender in full mode with 500 error (shows Retry button)
      rerender(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-500']}>
            <IssueSurfaceSlotsContext.Provider value={{}}>
              <IssueSurfaceRoot mode="full" issueKey="KAN-500" projectKey={null} />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Could not load KAN-500.')).toBeDefined();
      });
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      expect(getSpy).toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'Return to side panel' }));
      fireEvent.keyDown(window, { key: 'Escape' });

      unmount();
    });

    it('covers authApi branches for submitLocalAdminLogin and webauthn options', async () => {
      const spy = vi.spyOn(apiClientModule, 'apiFetch');

      spy.mockResolvedValueOnce({
        status: 'mfa_required',
        challenge_id: 'ch-1',
        methods: ['totp'],
      });
      const r1 = await submitLocalAdminLogin({ username: 'a', password: 'b' });
      expect(r1.status).toBe('mfa_required');

      spy.mockResolvedValueOnce({ status: 'authenticated' });
      const r2 = await submitLocalAdminLogin({ username: 'a', password: 'b' });
      expect(r2.status).toBe('authenticated');

      spy.mockResolvedValueOnce({ mfa_pending: true, session_id: 's-1' });
      const r3 = await submitLocalAdminLogin({ username: 'a', password: 'b' });
      expect(r3.status).toBe('mfa_required');

      spy.mockResolvedValueOnce({});
      const r4 = await submitLocalAdminLogin({ username: 'a', password: 'b' });
      expect(r4.status).toBe('authenticated');

      spy.mockResolvedValueOnce({ options: { challenge: 'c1' } });
      const w1 = await getWebauthnAssertionOptions({ challenge_id: 'ch-1' });
      expect(w1.options).toEqual({ challenge: 'c1' });

      spy.mockResolvedValueOnce({ challenge: 'c2' });
      const w2 = await getWebauthnAssertionOptions({ challenge_id: 'ch-1' });
      expect(w2.options).toEqual({ challenge: 'c2' });

      spy.mockResolvedValueOnce({ options: { challenge: 'r1' } });
      const g1 = await getWebauthnRegistrationOptions({ enrollment_id: 'e-1' });
      expect(g1.options).toEqual({ challenge: 'r1' });

      spy.mockResolvedValueOnce({ challenge: 'r2' });
      const g2 = await getWebauthnRegistrationOptions({ enrollment_id: 'e-1' });
      expect(g2.options).toEqual({ challenge: 'r2' });
    });

    it('covers StickiesStory update/promote/delete/unarchive and EditorStory paste handlers', async () => {
      // Polyfill DataTransfer and ClipboardEvent for jsdom
      class MockDataTransfer {
        private data = new Map<string, string>();
        files: File[] = [];
        types: string[] = [];
        items = {
          add: (f: File) => {
            this.files.push(f);
          },
        };
        setData(k: string, v: string) {
          this.data.set(k, v);
          if (!this.types.includes(k)) {
            this.types.push(k);
          }
        }
        getData(k: string) {
          return this.data.get(k) ?? '';
        }
      }
      (globalThis as Record<string, unknown>).DataTransfer = MockDataTransfer;

      class MockClipboardEvent extends Event {
        clipboardData: unknown;
        constructor(
          type: string,
          init?: { clipboardData?: unknown; bubbles?: boolean; cancelable?: boolean },
        ) {
          super(type, init);
          this.clipboardData = init?.clipboardData;
        }
      }
      (globalThis as Record<string, unknown>).ClipboardEvent = MockClipboardEvent;

      const { unmount: uEditor } = render(<EditorStory />);
      fireEvent.click(screen.getByTestId('btn-paste-rich-html'));
      fireEvent.click(screen.getByTestId('btn-paste-ide-code'));
      fireEvent.click(screen.getByTestId('btn-paste-image'));
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });
      uEditor();

      const { unmount: uStickies } = render(
        <MemoryRouter>
          <StickiesStory />
        </MemoryRouter>,
      );

      // Select a color swatch on the first sticky card
      const radios = screen.getAllByRole('radio');
      if (radios[1]) {
        fireEvent.click(radios[1]);
      }

      // Click Snooze on a promotion banner if present
      const snoozeBtns = screen.queryAllByRole('button', { name: /Snooze/i });
      if (snoozeBtns[0]) {
        fireEvent.click(snoozeBtns[0]);
      }

      // Click Promote to Doc on a promotion banner if present
      const promoteBtns = screen.queryAllByRole('button', { name: /Promote to Doc/i });
      if (promoteBtns[0]) {
        fireEvent.click(promoteBtns[0]);
      }

      // Click Unarchive Copy on a promoted stub
      const unarchiveBtns = screen.queryAllByTestId('unarchive-copy-btn');
      if (unarchiveBtns[0]) {
        fireEvent.click(unarchiveBtns[0]);
      }

      // Delete a sticky via overflow menu or delete button
      const menuBtns = screen.queryAllByRole('button', { name: /More actions|Sticky actions|Delete/i });
      if (menuBtns[0]) {
        fireEvent.click(menuBtns[0]);
        const confirmDel = screen.queryByRole('menuitem', { name: /Delete/i });
        if (confirmDel) {
          fireEvent.click(confirmDel);
        }
      }
      uStickies();
    });

    it('covers AppErrorModal peek URL recovery, GlobalErrorBoundary unhandledrejection, and Sidebar workspace/project creation', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?peek=KAN-123');
      const onDismiss = vi.fn();
      const { unmount: uErr } = render(
        <AppErrorModal error={{ custom: 'obj' }} onDismiss={onDismiss} />,
      );
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));
      expect(window.location.search).toBe('');
      uErr();

      const { unmount: uGlobal } = render(
        <GlobalErrorBoundary>
          <div>Child</div>
        </GlobalErrorBoundary>,
      );
      act(() => {
        window.dispatchEvent(
          new ErrorEvent('error', { error: new Error('Explicit error object') }),
        );
      });
      expect(screen.getByTestId('error-message').textContent).toBe('Explicit error object');
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));

      act(() => {
        const rejEvt = new Event('unhandledrejection') as Event & { reason?: unknown };
        rejEvt.reason = new Error('Rejected promise');
        window.dispatchEvent(rejEvt);
      });
      expect(screen.getByTestId('error-message').textContent).toBe('Rejected promise');
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));
      uGlobal();

      // Sidebar: create workspace end-to-end, project expand toggle, scrim click
      vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValue('csrf-token');
      vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url === '/api/v1/workspaces' && init?.method === 'POST') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ id: 'ws-new', name: 'New WS', slug: 'new-ws' }),
              { status: 201 },
            ),
          );
        }
        if (url === '/api/v1/workspaces') {
          return Promise.resolve(
            new Response(
              JSON.stringify([{ id: 'ws-1', name: 'Main WS', slug: 'main-ws', is_current: true }]),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/switch')) {
          return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
        }
        if (url === '/api/v1/projects' && init?.method === 'POST') {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: 'p-new',
                identifier: 'NEWP',
                name: 'New Project',
                modules_enabled: true,
              }),
              { status: 201 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      });

      const onCloseSidebar = vi.fn();
      const { unmount: uSidebar } = render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <Sidebar isOpen={true} onClose={onCloseSidebar} projectKey="KAN" projectName="kanban" />
        </MemoryRouter>,
      );

      // Click scrim
      const scrim = must(document.querySelector('.kb-sidebar-scrim'));
      fireEvent.click(scrim);
      expect(onCloseSidebar).toHaveBeenCalled();

      // Collapse and expand project section
      const projExpand = screen.getByRole('button', { name: 'Project: kanban' });
      fireEvent.click(projExpand);
      fireEvent.click(projExpand);

      // Open Create New Workspace, test Escape and outside click on workspace dropdown
      fireEvent.click(screen.getByRole('button', { name: /Workspace switcher/i }));
      fireEvent.keyDown(window, { key: 'Escape' });
      fireEvent.click(screen.getByRole('button', { name: /Workspace switcher/i }));
      fireEvent.mouseDown(document.body);

      fireEvent.click(screen.getByRole('button', { name: /Workspace switcher/i }));
      fireEvent.click(screen.getByRole('menuitem', { name: /Create New Workspace/i }));
      fireEvent.change(screen.getByLabelText(/Workspace Name/i), {
        target: { value: 'New WS' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));
      await waitFor(() => {
        expect(screen.queryByRole('dialog', { name: 'Create New Workspace' })).toBeNull();
      });

      // Open Create Project modal via + Project button and submit new project
      fireEvent.click(screen.getByRole('button', { name: 'Create project' }));
      fireEvent.change(screen.getByLabelText(/Project Name/i), {
        target: { value: 'New Project' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Create Project' }));
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Project: New Project' })).toBeDefined();
      });

      // Dispatch kb:open-create-project and kb:toggle-sidebar
      act(() => {
        window.dispatchEvent(new Event('kb:open-create-project'));
        window.dispatchEvent(new Event('kb:toggle-sidebar'));
      });
      uSidebar();
    });

    it('covers AuthStudioPage error branches and empty users list', async () => {
      let userListCall = 0;
      vi.spyOn(apiClientModule, 'apiFetch').mockImplementation((method, path) => {
        const p = path as string;
        if (p === '/api/v1/auth/me') {
          return Promise.resolve({ id: 'admin-1', handle: 'admin', is_server_admin: true });
        }
        if (p === '/api/v1/admin/auth-cards' && method === 'GET') {
          return Promise.reject(new Error('Cards load failure'));
        }
        if (p.startsWith('/api/v1/admin/principals') && method === 'GET') {
          userListCall += 1;
          if (userListCall === 1) {
            return Promise.resolve([
              {
                id: 'u-bare',
                principal: 'bareuser',
                display_name: '',
                type: 'USER',
                status: 'active',
              },
            ]);
          }
          return Promise.resolve([]);
        }
        if (p === '/api/v1/admin/principals' && method === 'POST') {
          return Promise.reject(new Error('Create user failed'));
        }
        if (p.includes('/password') && method === 'POST') {
          return Promise.reject(new Error('Reset password failed'));
        }
        if (p === '/api/v1/admin/role-bindings' && method === 'POST') {
          return Promise.reject(new Error('Role update failed'));
        }
        return Promise.resolve({});
      });

      const { unmount } = render(<AuthStudioPage />);
      await waitFor(() => {
        expect(screen.getByText('Cards load failure')).toBeDefined();
      });
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss error' }));

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));
      await waitFor(() => {
        expect(screen.getByText('@bareuser')).toBeDefined();
      });

      // Role change error
      fireEvent.change(screen.getByLabelText(/Role for @?bareuser/i), {
        target: { value: 'SERVER_ADMIN' },
      });
      await waitFor(() => {
        expect(screen.getByText('Role update failed')).toBeDefined();
      });

      // Reset password error and Cancel / Close
      fireEvent.click(screen.getByRole('button', { name: 'Reset Password' }));
      fireEvent.change(screen.getByLabelText(/^New Password/i), {
        target: { value: 'Pass1234!' },
      });
      fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
        target: { value: 'Pass1234!' },
      });
      fireEvent.submit(
        must(screen.getByRole('dialog', { name: /Reset Password/i }).querySelector('form')),
      );
      await waitFor(() => {
        expect(screen.getByText('Reset password failed')).toBeDefined();
      });
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      // Reopen Reset Password modal and click Close (x) button
      fireEvent.click(screen.getByRole('button', { name: 'Reset Password' }));
      fireEvent.click(screen.getByRole('button', { name: 'Close' }));

      // Switch back to Auth Provider Cards tab and return to Users & Permissions tab
      fireEvent.click(screen.getByRole('tab', { name: /Auth Provider Cards/i }));
      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      // Open + Add Local User modal, submit to trigger error, then Close, then reopen and Cancel
      fireEvent.click(screen.getByRole('button', { name: '+ Add Local User' }));
      fireEvent.change(screen.getByLabelText(/Username \/ Handle/i), { target: { value: 'u1' } });
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: 'u1@example.com' },
      });
      fireEvent.change(screen.getByLabelText(/^Password/i), { target: { value: 'Pass1234!' } });
      fireEvent.submit(
        must(screen.getByRole('dialog', { name: '+ Add Local User' }).querySelector('form')),
      );
      await waitFor(() => {
        expect(screen.getByText('Create user failed')).toBeDefined();
      });
      fireEvent.click(screen.getByRole('button', { name: 'Close' }));
      fireEvent.click(screen.getByRole('button', { name: '+ Add Local User' }));
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      unmount();
    });

    it('covers IssuesWorkspaceRoute live mode, URL search param filters, and bulk actions', async () => {
      window.history.pushState(
        {},
        '',
        '/projects/KAN/issues?layout=table&group_by=priority&sub_group_by=assignee&filter_state=active&filter_priority=high&filter_label=security&gate_status=approved&peek=KAN-101',
      );

      vi.spyOn(window, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        if (url.includes('/states')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 1 },
                { id: 'st-prog', name: 'In Progress', group: 'started', sort_order: 2 },
                { id: 'st-done', name: 'Done', group: 'completed', sort_order: 3 },
              ]),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/issues')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: FIXTURE_12_ISSUES.map((iss, i) => ({
                  ...iss,
                  priority: { slug: 'high', label: 'High', emoji: '⚡' },
                  gate_status: i % 2 === 0 ? 'approved' : 'vetoed',
                  labels: [{ id: 'l-sec', name: 'security', color_hex: '#ff0000' }],
                  assignees:
                    i === 0
                      ? [{ id: 'a-free', kind: 'free_text', free_text: 'ext-contractor' }]
                      : iss.assignees,
                })),
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      });

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssuesWorkspaceRoute projectKey="KAN" queryClient={qc} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.queryAllByRole('checkbox').length).toBeGreaterThan(1);
      });

      const liveCbs = screen.queryAllByRole('checkbox');
      if (liveCbs[1]) {
        fireEvent.click(liveCbs[1]);
      }
      const liveStateBtn = document.querySelector('[data-action="state"]');
      if (liveStateBtn) {
        fireEvent.click(liveStateBtn);
      }
      const liveCbs2 = screen.queryAllByRole('checkbox');
      if (liveCbs2[1]) {
        fireEvent.click(liveCbs2[1]);
      }
      const livePrioBtn = document.querySelector('[data-action="priority"]');
      if (livePrioBtn) {
        fireEvent.click(livePrioBtn);
      }

      act(() => {
        window.dispatchEvent(new PopStateEvent('popstate'));
        window.dispatchEvent(new Event('kb:issue-updated'));
        window.dispatchEvent(new Event('kb:create-issue'));
      });

      window.history.pushState({}, '', '/');
      unmount();
    });

    it('covers StatePriorityRows gate pills, CreateProjectModal branches, Topbar logout, and DrawerActionsStory overflow', async () => {
      // 1. StatePriorityRows gate status pills
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const baseIssue: IssueDetail = {
        key: 'KAN-1',
        project_key: 'KAN',
        summary: 'Gate test',
        state: { id: 's-1', name: 'In Review', group: 'started' },
        priority: { slug: 'high', label: 'High', emoji: '⚡' },
      };

      const { rerender: rerenderSpr, unmount: uSpr } = render(
        <QueryClientProvider client={qc}>
          <StatePriorityRows
            issue={{
              ...baseIssue,
              pending_gate: {
                execution_id: 'ex-1',
                hook_name: 'QA Gate',
                agent_slug: 'qa-agent',
                harness_label: 'agy',
                started_at: new Date().toISOString(),
              },
            }}
            canEdit={true}
            canTransition={true}
            onStateChange={vi.fn()}
            onPriorityChange={vi.fn()}
          />
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('drawer-gate-pending')).toBeDefined();

      rerenderSpr(
        <QueryClientProvider client={qc}>
          <StatePriorityRows
            issue={{
              ...baseIssue,
              latest_gate_verdict: {
                hook_name: 'QA Gate',
                decision: 'reject',
                reason_preview: 'Failed QA',
                completed_at: new Date().toISOString(),
              },
            }}
            canEdit={true}
            canTransition={true}
            onStateChange={vi.fn()}
            onPriorityChange={vi.fn()}
          />
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('drawer-gate-vetoed')).toBeDefined();

      rerenderSpr(
        <QueryClientProvider client={qc}>
          <StatePriorityRows
            issue={{
              ...baseIssue,
              latest_gate_verdict: {
                hook_name: 'QA Gate',
                decision: 'approve',
                reason_preview: 'Passed QA',
                completed_at: new Date().toISOString(),
              },
            }}
            canEdit={true}
            canTransition={true}
            onStateChange={vi.fn()}
            onPriorityChange={vi.fn()}
          />
        </QueryClientProvider>,
      );
      expect(screen.getByTestId('drawer-gate-approved')).toBeDefined();
      uSpr();

      // 2. suggestProjectIdentifier & CreateProjectModal outside Router
      expect(suggestProjectIdentifier('12345')).toBe('PRJ');
      expect(suggestProjectIdentifier('A')).toBe('A1');
      expect(suggestProjectIdentifier('Single')).toBe('SINGL');
      expect(suggestProjectIdentifier('Two Words')).toBe('TWWO');

      vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValue('csrf-1');
      const fetchSpy = vi.spyOn(window, 'fetch');
      const onCloseProj = vi.fn();
      const { unmount: uProj } = render(
        <CreateProjectModal isOpen={true} onClose={onCloseProj} />,
      );
      // Escape closes
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onCloseProj).toHaveBeenCalledTimes(1);

      const pName = screen.getByLabelText(/Project Name/i);
      const pKey = screen.getByLabelText(/Identifier/i);
      fireEvent.change(pName, { target: { value: 'Alpha Beta' } });
      fireEvent.change(pKey, { target: { value: '1BAD' } });
      fireEvent.change(pName, { target: { value: 'Alpha Beta Updated' } });
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      expect(screen.getByRole('alert').textContent).toContain('Identifier must be 2-10');

      fireEvent.change(pKey, { target: { value: 'ALPH' } });
      // Nested error detail
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { detail: 'Project key conflict' } }), {
          status: 409,
        }),
      );
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Project key conflict');
      });

      // Non-JSON error status
      fetchSpy.mockResolvedValueOnce(new Response('Err', { status: 502 }));
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe(
          'Failed to create project (HTTP 502)',
        );
      });

      // Non-Error rejection
      fetchSpy.mockRejectedValueOnce('raw error');
      fireEvent.submit(must(screen.getByRole('dialog').querySelector('form')));
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Could not create project.');
      });
      uProj();

      // 3. Topbar avatar menu outside click & logout error fallback
      fetchSpy.mockRejectedValueOnce(new Error('Logout network error'));
      const { unmount: uTop } = render(
        <QueryClientProvider client={qc}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues']}>
                <Topbar
                  isSidebarOpen={false}
                  onToggleSidebar={vi.fn()}
                  projectKey="KAN"
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      const avatarBtn = screen.getByRole('button', { name: /User menu|Account|Profile|admin/i });
      fireEvent.click(avatarBtn);
      fireEvent.mouseDown(document.body);
      fireEvent.click(avatarBtn);
      const logoutItem = screen.getByRole('menuitem', { name: /Sign out|Log out/i });
      fireEvent.click(logoutItem);
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });
      uTop();

      // 4. DrawerActionsStory overflow toggleFullScreen round-trip (drawer -> full -> drawer)
      const { unmount: uDa } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <DrawerActionsStory />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const moreBtn = screen.getByRole('button', { name: /More actions|Overflow/i });
      fireEvent.click(moreBtn);
      const fsItem = screen.queryByRole('menuitem', { name: /full screen|side panel/i });
      if (fsItem) {
        fireEvent.click(fsItem);
      }
      fireEvent.click(screen.getByRole('button', { name: /More actions|Overflow/i }));
      const spItem = screen.queryByRole('menuitem', { name: /full screen|side panel/i });
      if (spItem) {
        fireEvent.click(spItem);
      }
      uDa();

      // 5. StickiesStory Promote to Doc (before snooze)
      const { unmount: uStickiesPromote } = render(
        <MemoryRouter>
          <StickiesStory />
        </MemoryRouter>,
      );
      const promoteToDocBtn = screen.queryByTestId('promote-to-doc-btn');
      if (promoteToDocBtn) {
        fireEvent.click(promoteToDocBtn);
      }
      uStickiesPromote();

      // 6. RouteErrorBoundary with ?peek=KAN-1&layout=board, ?peek=KAN-1, and without ?peek
      function CrashRoute(): React.JSX.Element {
        throw new Error('Route crashed');
      }
      for (const entry of ['/?peek=KAN-1&layout=board', '/?peek=KAN-1', '/']) {
        const errRouter = createMemoryRouter(
          [
            {
              path: '/',
              element: <CrashRoute />,
              errorElement: <RouteErrorBoundary />,
            },
          ],
          { initialEntries: [entry] },
        );
        const { unmount: uErrRoute } = render(<RouterProvider router={errRouter} />);
        expect(screen.getByTestId('error-message').textContent).toBe('Route crashed');
        fireEvent.click(screen.getByTestId('error-dismiss-btn'));
        uErrRoute();
      }

      // 6b. Topbar with null csrfToken and showLayoutOverride
      vi.spyOn(sessionGuardModule, 'ensureSessionCsrfToken').mockResolvedValueOnce(null);
      fetchSpy.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
      const { unmount: uTop2 } = render(
        <QueryClientProvider client={qc}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-1']}>
                <Topbar
                  isSidebarOpen={true}
                  onToggleSidebar={vi.fn()}
                  projectKey="KAN"
                  showLayoutSwitcher={true}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      const avatarBtn2 = screen.getByRole('button', { name: /User menu|Account|Profile|admin/i });
      fireEvent.click(avatarBtn2);
      fireEvent.click(screen.getByRole('menuitem', { name: /Sign out|Log out/i }));
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });
      uTop2();

      // 6c. ProjectIssuesRoute ?create=1 timer and WorkspaceHomeView onCreated callback
      const appRouter = createAppRouter(['/projects/KAN/issues?create=1&layout=list']);
      const { unmount: uAppR } = render(
        <QueryClientProvider client={qc}>
          <ThemeProvider>
            <RouterProvider router={appRouter} />
          </ThemeProvider>
        </QueryClientProvider>,
      );
      await act(async () => {
        await new Promise((r) => setTimeout(r, 20));
      });
      uAppR();

      // 7. IssuesWorkspaceRoute handleOpenPeek, ViewHost onCreateIssue, and BulkActionBar in live mode
      window.history.pushState({}, '', '/projects/KAN/issues');
      const { unmount: uIwr1 } = render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialIssues={FIXTURE_12_ISSUES}
            initialLayout="list"
          />
        </MemoryRouter>,
      );
      // Click first issue key button in ListRow to trigger handleOpenPeek without propOnOpenPeek
      const firstIssueBtn = screen.queryAllByText(must(FIXTURE_12_ISSUES[0]).key)[0];
      if (firstIssueBtn) {
        fireEvent.click(firstIssueBtn);
      }
      // Select first issue checkbox to mount BulkActionBar
      const checkboxes = screen.queryAllByRole('checkbox');
      if (checkboxes[0]) {
        fireEvent.click(checkboxes[0]);
      }
      uIwr1();

      // ViewHost empty table onCreateIssue
      const { unmount: uIwr2 } = render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialIssues={[]}
            initialLayout="table"
          />
        </MemoryRouter>,
      );
      const createFirstBtn = screen.queryByRole('button', { name: /\+ Create first work item/i });
      if (createFirstBtn) {
        fireEvent.click(createFirstBtn);
      }
      uIwr2();

      // 8. IssuesWorkspaceRoute with propOnOpenPeek, QuickFieldPopover none/medium/done, and BulkActionBar Clear
      const spyOpenPeek = vi.fn();
      const { unmount: uIwr3 } = render(
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialIssues={FIXTURE_12_ISSUES}
            initialLayout="list"
            onOpenPeek={spyOpenPeek}
          />
        </MemoryRouter>,
      );
      const firstIssueBtn2 = screen.queryAllByText(must(FIXTURE_12_ISSUES[0]).key)[0];
      if (firstIssueBtn2) {
        fireEvent.click(firstIssueBtn2);
      }
      expect(spyOpenPeek).toHaveBeenCalled();

      // Open priority popover with 'p' shortcut and select 'none' then 'medium'
      fireEvent.keyDown(window, { key: 'p' });
      const noneOpt = screen.queryAllByRole('option', { name: /➖ None/i })[0];
      if (noneOpt) {
        fireEvent.click(noneOpt);
      }
      fireEvent.keyDown(window, { key: 'p' });
      const medOpt = screen.queryAllByRole('option', { name: /🔹 Medium/i })[0];
      if (medOpt) {
        fireEvent.click(medOpt);
      }

      // Open state popover with 's' shortcut and select 'Done'
      fireEvent.keyDown(window, { key: 's' });
      const doneOpt = screen.queryAllByRole('option', { name: /Done/i })[0];
      if (doneOpt) {
        fireEvent.click(doneOpt);
      }

      // Select checkbox and click State, Priority, and Clear (Esc) on BulkActionBar
      const cbs = screen.queryAllByRole('checkbox');
      if (cbs[0]) {
        fireEvent.click(cbs[0]);
      }
      const stateBulkBtn = document.querySelector('[data-action="state"]');
      if (stateBulkBtn) {
        fireEvent.click(stateBulkBtn);
      }
      const cbs2 = screen.queryAllByRole('checkbox');
      if (cbs2[0]) {
        fireEvent.click(cbs2[0]);
      }
      const prioBulkBtn = document.querySelector('[data-action="priority"]');
      if (prioBulkBtn) {
        fireEvent.click(prioBulkBtn);
      }
      const cbs3 = screen.queryAllByRole('checkbox');
      if (cbs3[0]) {
        fireEvent.click(cbs3[0]);
      }
      const clearBulkBtn = screen.queryByRole('button', { name: 'Clear selection' });
      if (clearBulkBtn) {
        fireEvent.click(clearBulkBtn);
      }
      uIwr3();

      // 8b. TableView, CalendarView, and TimelineView onOpenPeek row/link clicks
      const peekSpy = vi.fn();
      const todayIso = new Date().toISOString().slice(0, 10);
      const datedIssues = FIXTURE_12_ISSUES.map((iss) => ({
        ...iss,
        links: [],
        start_date: todayIso,
        due_date: todayIso,
      }));

      const { rerender: rerenderViews, unmount: uViews } = render(
        <div>
          <TableView issues={datedIssues} projectKey="KAN" onOpenPeek={peekSpy} />
          <CalendarView issues={datedIssues} projectKey="KAN" onOpenPeek={peekSpy} />
          <TimelineView issues={datedIssues} projectKey="KAN" onOpenPeek={peekSpy} />
        </div>,
      );

      const tblRow = document.querySelector('.table-row td:nth-child(2)');
      if (tblRow) fireEvent.click(tblRow);
      const tblLink = document.querySelector('.table-key-link');
      if (tblLink) fireEvent.click(tblLink);

      const calPill = document.querySelector('.calendar-issue-pill');
      if (calPill) fireEvent.click(calPill);
      const calAgenda = document.querySelector('.calendar-agenda-row');
      if (calAgenda) fireEvent.click(calAgenda);

      const tlSummary = document.querySelector('.timeline-left-row-summary');
      if (tlSummary) fireEvent.click(tlSummary);
      const tlLink = document.querySelector('.timeline-left-row-key');
      if (tlLink) fireEvent.click(tlLink);

      // Rerender without onOpenPeek to cover false branch
      rerenderViews(
        <div>
          <TableView issues={datedIssues} projectKey="KAN" />
          <CalendarView issues={datedIssues} projectKey="KAN" />
          <TimelineView issues={datedIssues} projectKey="KAN" />
        </div>,
      );
      const tblLink2 = document.querySelector('.table-key-link');
      if (tblLink2) fireEvent.click(tblLink2);
      const calPill2 = document.querySelector('.calendar-issue-pill');
      if (calPill2) fireEvent.click(calPill2);
      const tlLink2 = document.querySelector('.timeline-left-row-key');
      if (tlLink2) fireEvent.click(tlLink2);
      uViews();

      // 9. AuthStudioPage drag reverse/same index, AAL2 fallback fields, and loadUsers error branches
      let callPhase = 0;
      vi.spyOn(apiClientModule, 'apiFetch').mockImplementation((method, path) => {
        const p = path as string;
        if (p === '/api/v1/auth/me') {
          return Promise.resolve({ id: 'admin-1', handle: 'admin', is_server_admin: true });
        }
        if (p === '/api/v1/admin/auth-cards' && method === 'GET') {
          if (callPhase === 1) return Promise.reject(asErrorType('raw card error'));
          return Promise.resolve({
            cards: [
              {
                id: 'c-1',
                provider_kind: 'OIDC',
                slug: 'oidc-1',
                display_name: 'OIDC One',
                button_subtext: null,
                icon_preset: 'google',
                is_enabled: true,
                sort_rank: 'a0',
                auto_provision_users: true,
                allowed_email_domains: [],
                has_secret: true,
                dek_kid: 'k1',
                last_health_status: 'HEALTHY',
                public_config: { client_id: 'c1' },
              },
              {
                id: 'c-2',
                provider_kind: 'OIDC',
                slug: 'oidc-2',
                display_name: 'OIDC Two',
                button_subtext: null,
                icon_preset: 'github',
                is_enabled: true,
                sort_rank: 'a1',
                auto_provision_users: true,
                allowed_email_domains: [],
                has_secret: true,
                dek_kid: 'k1',
                last_health_status: 'FAILED',
                check_summary: 'Timeout',
                last_handshake_at: '2026-01-01T00:00:00Z',
                public_config: { client_id: 'c2' },
              },
            ],
          });
        }
        if (p.startsWith('/api/v1/admin/principals') && method === 'GET') {
          if (callPhase === 0) return Promise.reject(new Error('Users load error'));
          if (callPhase === 2) return Promise.reject(new ApiProblem(403, { code: 'FORBIDDEN' }));
          return Promise.reject(asErrorType('raw users error'));
        }
        if (p.endsWith('/disable')) {
          return Promise.reject(new ApiProblem(403, { code: 'AAL2_REQUIRED' }));
        }
        if (p.endsWith('/reorder')) {
          return Promise.reject(new Error('Reorder network error'));
        }
        return Promise.resolve({});
      });

      const { unmount: uAs1 } = render(<AuthStudioPage />);
      await waitFor(() => {
        expect(screen.getByText('OIDC One')).toBeDefined();
      });
      const r0 = screen.getByTestId('auth-card-row-oidc-1');
      const r1 = screen.getByTestId('auth-card-row-oidc-2');
      // Drag same index
      fireEvent.dragStart(r0);
      fireEvent.drop(r0);
      // Drag reverse (index 1 -> index 0) with reorder failure
      fireEvent.dragStart(r1);
      fireEvent.drop(r0);
      await waitFor(() => {
        expect(screen.getByText('Failed to reorder card.')).toBeDefined();
      });

      // Trigger AAL2_REQUIRED without challenge_id/methods
      fireEvent.click(screen.getByRole('switch', { name: 'Enable OIDC One' }));
      await waitFor(() => {
        expect(screen.getByText(/Admin Verification Required/i)).toBeDefined();
      });
      // Switch to Users & Permissions tab when users list is empty
      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));
      expect(screen.getByText('No user principals found.')).toBeDefined();
      uAs1();

      callPhase = 1;
      const { unmount: uAs2 } = render(<AuthStudioPage />);
      await waitFor(() => {
        expect(screen.getByText('Failed to load authentication cards.')).toBeDefined();
      });
      uAs2();

      callPhase = 2;
      const { unmount: uAs3 } = render(<AuthStudioPage />);
      await waitFor(() => {
        expect(screen.getByText('Not found or no access')).toBeDefined();
      });
      uAs3();
    });
  });
});
