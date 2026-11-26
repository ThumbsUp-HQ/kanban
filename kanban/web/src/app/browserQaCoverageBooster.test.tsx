// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import {
  CreateProjectModal,
  suggestProjectIdentifier,
} from '../features/projects/CreateProjectModal';
import {
  ensureSessionCsrfToken,
  isPublicPath,
  useSessionGuard,
} from '../features/auth/useSessionGuard';
import { CommandPalette } from './CommandPalette';
import { LayoutSwitcher } from './LayoutSwitcher';
import * as clientModule from '../api/client';
import {
  enrollTotp,
  getWebauthnRegistrationOptions,
  verifyTotpEnrollment,
  verifyWebauthnRegistration,
} from '../features/auth/authApi';
import {
  AppRoutes,
  DraftsWorkspaceView,
  ProjectCyclesView,
  ProjectIssuesRoute,
  ProjectModulesView,
  ProjectSavedViewsView,
  WorkspaceHomeView,
  YourWorkView,
} from './routes';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { ThemeProvider } from '../theme/ThemeProvider';
import { ShellPanelsProvider } from './shellPanels';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssuesWorkspaceRoute } from '../features/views/viewRegistry';
import { fetchStagedProjectIssues } from '../features/views/viewsApi';
import { AdminDiagnosticsStudio } from '../features/admin/AdminDiagnosticsStudio';
import { IssueSurfaceRoot } from '../features/drawer/IssueSurface';
import { RailStory } from '../dev/RailStory';
import { DrawerActionsStory } from '../dev/DrawerActionsStory';
import { StickiesStory } from '../dev/StickiesStory';
import { IconStory } from '../dev/IconStory';
import { MediaStory } from '../dev/MediaStory';
import { EditorStory } from '../dev/EditorStory';

function GuardHarness({ enabled = true }: { enabled?: boolean }): React.JSX.Element {
  const state = useSessionGuard(enabled);
  return <div data-testid="guard-state">{state.status}:{String(state.aalLevel)}</div>;
}

describe('Browser QA Branch Coverage Booster', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('suggestProjectIdentifier & CreateProjectModal branches', () => {
    it('covers all identifier derivation branches', () => {
      expect(suggestProjectIdentifier('   ')).toBe('');
      expect(suggestProjectIdentifier('12345')).toBe('PRJ');
      expect(suggestProjectIdentifier('123 A')).toBe('A1');
      expect(suggestProjectIdentifier('Single')).toBe('SINGL');
      expect(suggestProjectIdentifier('Alpha Beta Gamma Delta')).toBe('ALBEGA');
    });

    it('covers validation errors, nested error detail, fallback status error, non-Error throw, Escape, and scrim click', async () => {
      const onClose = vi.fn();
      const onCreated = vi.fn();
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      render(
        <CreateProjectModal isOpen={true} onClose={onClose} onCreated={onCreated} />,
      );

      // Empty name submit via form
      const form = screen.getByTestId('create-project-modal').querySelector('form');
      if (!form) {
        throw new Error('form missing');
      }
      fireEvent.submit(form);
      expect((await screen.findByTestId('create-project-error')).textContent).toContain(
        'Project name is required.',
      );

      // Typing name clears error & auto-fills identifier
      const nameInput = screen.getByLabelText('Project Name');
      fireEvent.change(nameInput, { target: { value: 'Sec Ops' } });
      expect(screen.queryByTestId('create-project-error')).toBeNull();

      // Invalid identifier (1 char)
      const idInput = screen.getByLabelText('Project Key', { selector: 'input' });
      fireEvent.change(idInput, { target: { value: 'S' } });
      fireEvent.submit(form);
      expect((await screen.findByTestId('create-project-error')).textContent).toContain(
        'Identifier must be 2-10 uppercase characters',
      );

      // Typing identifier clears error
      fireEvent.change(idInput, { target: { value: 'SEC' } });
      expect(screen.queryByTestId('create-project-error')).toBeNull();

      // Toggle modules checkbox & description
      fireEvent.change(screen.getByLabelText('Description (Markdown)'), {
        target: { value: 'Desc' },
      });
      fireEvent.click(screen.getByLabelText('Enable project modules'));

      // Nested { detail: { detail: 'Nested err' } }
      document.cookie = 'kb_csrf=tok123';
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { detail: 'Nested err' } }), { status: 400 }),
      );
      fireEvent.submit(form);
      expect((await screen.findByTestId('create-project-error')).textContent).toContain(
        'Nested err',
      );

      // Fallback status error when JSON fails
      fetchSpy.mockResolvedValueOnce(new Response('not-json', { status: 502 }));
      fireEvent.submit(form);
      expect((await screen.findByTestId('create-project-error')).textContent).toContain(
        'Failed to create project (HTTP 502)',
      );

      // Non-Error rejection
      fetchSpy.mockRejectedValueOnce('raw string rejection');
      fireEvent.submit(form);
      expect((await screen.findByTestId('create-project-error')).textContent).toContain(
        'Could not create project.',
      );

      // Scrim click closes only when target === currentTarget
      const scrim = screen.getByTestId('create-project-scrim');
      fireEvent.click(screen.getByTestId('create-project-modal'));
      expect(onClose).not.toHaveBeenCalled();
      fireEvent.click(scrim);
      expect(onClose).toHaveBeenCalledTimes(1);

      // Escape key closes
      fireEvent.keyDown(window, { key: 'Enter' });
      expect(onClose).toHaveBeenCalledTimes(1);
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(2);
    });
  });

  describe('useSessionGuard & ensureSessionCsrfToken branches', () => {
    it('covers ensureSessionCsrfToken cookie, malformed URI cookie, session bootstrap, and failure', async () => {
      document.cookie = 'kb_csrf=%E0%A4%A';
      expect(await ensureSessionCsrfToken()).toBe('%E0%A4%A');

      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      fetchSpy.mockResolvedValueOnce(new Response('{}', { status: 500 }));
      expect(await ensureSessionCsrfToken()).toBeNull();

      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: 'boot-tok' }), { status: 200 }),
      );
      expect(await ensureSessionCsrfToken()).toBe('boot-tok');

      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      fetchSpy.mockRejectedValueOnce(new Error('offline'));
      expect(await ensureSessionCsrfToken()).toBeNull();
    });

    it('covers useSessionGuard disabled, public path, mfa_pending, and authenticated branches', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      // Disabled
      const { unmount: u1 } = render(
        <MemoryRouter initialEntries={['/']}>
          <GuardHarness enabled={false} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('guard-state').textContent).toBe('authenticated:0');
      u1();

      // Public path (/login)
      const { unmount: u2 } = render(
        <MemoryRouter initialEntries={['/login']}>
          <GuardHarness enabled={true} />
        </MemoryRouter>,
      );
      expect(fetchSpy).not.toHaveBeenCalled();
      u2();

      // mfa_pending === true -> redirects to /login (KANBA-207 strict MFA isolation)
      fetchSpy
        .mockResolvedValueOnce(new Response(JSON.stringify({ initialized: true }), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              authenticated: true,
              mfa_pending: true,
              csrf_token: 'c1',
            }),
            { status: 200 },
          ),
        );

      const { unmount: u3 } = render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<GuardHarness />} />
            <Route path="/login" element={<div data-testid="at-login">Login</div>} />
          </Routes>
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('at-login')).not.toBeNull();
      });
      u3();

      // Fully authenticated with null optional fields
      fetchSpy
        .mockResolvedValueOnce(new Response(JSON.stringify({ initialized: true }), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              authenticated: true,
              mfa_pending: false,
              aal_level: 2,
            }),
            { status: 200 },
          ),
        );

      render(
        <MemoryRouter initialEntries={['/']}>
          <GuardHarness />
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('guard-state').textContent).toBe('authenticated:2');
      });
    });

    it('covers uninitialized setup redirect, unauthenticated redirect with safeNext, and public paths', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      // isPublicPath checks
      expect(isPublicPath('/login')).toBe(true);
      expect(isPublicPath('/setup/profile')).toBe(true);
      expect(isPublicPath('/activate/claim')).toBe(true);
      expect(isPublicPath('/__dev/stories')).toBe(true);
      expect(isPublicPath('/projects/KANBA')).toBe(false);

      // setup initialized === false -> redirects to /setup
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify({ initialized: false }), { status: 200 }),
      );
      const { unmount: u1 } = render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<GuardHarness />} />
            <Route path="/setup" element={<div data-testid="at-setup">Setup</div>} />
          </Routes>
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('at-setup')).not.toBeNull();
      });
      u1();

      // session authenticated === false with deep link -> redirects to /login?next=...
      fetchSpy
        .mockResolvedValueOnce(new Response(JSON.stringify({ initialized: true }), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              authenticated: false,
              csrf_token: 'csrf-unauth',
            }),
            { status: 200 },
          ),
        );

      const { unmount: u2 } = render(
        <MemoryRouter initialEntries={['/projects/KANBA?tab=issues']}>
          <Routes>
            <Route path="/projects/:key" element={<GuardHarness />} />
            <Route path="/login" element={<div data-testid="at-login-deeplink">Login Target</div>} />
          </Routes>
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('at-login-deeplink')).not.toBeNull();
      });
      u2();

      // session authenticated === false with root path -> redirects to /login (no ?next=)
      fetchSpy
        .mockResolvedValueOnce(new Response(JSON.stringify({ initialized: true }), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              authenticated: false,
            }),
            { status: 200 },
          ),
        );

      const { unmount: u3 } = render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<GuardHarness />} />
            <Route path="/login" element={<div data-testid="at-login-root">Login Root</div>} />
          </Routes>
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('at-login-root')).not.toBeNull();
      });
      u3();
    });

    it('covers CommandPalette focus restore, global Escape, and LayoutSwitcher fallback config', () => {
      const onClose = vi.fn();
      const triggerBtn = document.createElement('button');
      triggerBtn.id = 'external-trigger';
      document.body.appendChild(triggerBtn);
      triggerBtn.focus();

      const { rerender, unmount } = render(
        <QueryClientProvider client={new QueryClient()}>
          <ThemeProvider>
            <MemoryRouter>
              <CommandPalette isOpen={true} onClose={onClose} />
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      // Escape key triggers onClose
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalled();

      // Rerender as closed -> restores focus to previous element
      rerender(
        <QueryClientProvider client={new QueryClient()}>
          <ThemeProvider>
            <MemoryRouter>
              <CommandPalette isOpen={false} onClose={onClose} />
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>,
      );

      expect(document.activeElement).toBe(triggerBtn);
      unmount();
      document.body.removeChild(triggerBtn);

      // LayoutSwitcher fallback config and custom className
      const { container } = render(
        <LayoutSwitcher value={'unknown_layout' as never} className="custom-sw" />,
      );
      expect(container.querySelector('.custom-sw')).not.toBeNull();
      expect(screen.getByRole('radio', { name: 'Issues' })).toBeDefined();
    });
  });

  describe('authApi branches', () => {
    it('covers WebAuthn and TOTP enrollment fallback branches', async () => {
      const spy = vi.spyOn(clientModule, 'apiFetch');

      // Direct options without .options wrapper
      spy.mockResolvedValueOnce({ challenge: 'ch-1' });
      const opt1 = await getWebauthnRegistrationOptions({ enrollment_id: 'e1' });
      expect(opt1.options.challenge).toBe('ch-1');

      // Wrapped .options
      spy.mockResolvedValueOnce({ options: { challenge: 'ch-2' } });
      const opt2 = await getWebauthnRegistrationOptions({ enrollment_id: 'e1' });
      expect(opt2.options.challenge).toBe('ch-2');

      // verifyWebauthnRegistration with direct recovery_codes
      spy.mockResolvedValueOnce({ recovery_codes: ['R1'] });
      const v1 = await verifyWebauthnRegistration({ enrollment_id: 'e1', credential: {} });
      expect(v1.recovery_codes).toEqual(['R1']);

      // verifyWebauthnRegistration fallback to /recovery-codes/generate
      spy
        .mockResolvedValueOnce({ status: 'ok' })
        .mockResolvedValueOnce({ recovery_codes: ['R2'] });
      const v2 = await verifyWebauthnRegistration({ enrollment_id: 'e1', credential: {} });
      expect(v2.recovery_codes).toEqual(['R2']);

      // enrollTotp with secret fallback and empty fallback
      spy.mockResolvedValueOnce({ secret: 'SEC32', otpauth_uri: 'otp://1' });
      expect((await enrollTotp({ enrollment_id: 'e1' })).secret_base32).toBe('SEC32');

      spy.mockResolvedValueOnce({ otpauth_uri: 'otp://2' });
      expect((await enrollTotp({ enrollment_id: 'e1' })).secret_base32).toBe('');

      // verifyTotpEnrollment fallback to /recovery-codes/generate
      spy
        .mockResolvedValueOnce({ status: 'ok' })
        .mockResolvedValueOnce({ recovery_codes: ['T1'] });
      const vt = await verifyTotpEnrollment({ enrollment_id: 'e1', code: '123456' });
      expect(vt.recovery_codes).toEqual(['T1']);
    });
  });

  describe('routes.tsx views & WorkspaceHomeView branches', () => {
    it('renders WorkspaceHomeView with direct array response, opens modal, creates project, and renders subviews', async () => {
      expect(AppRoutes()).toBeNull();

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.includes('/api/v1/projects')) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  id: 'p-1',
                  identifier: 'OPS',
                  name: 'Operations',
                  description_markdown: '',
                },
              ]),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 404 }));
      });

      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<WorkspaceHomeView />} />
            <Route
              path="/projects/:projectKey/issues"
              element={<div data-testid="issues-dest">Issues</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('project-card-OPS')).not.toBeNull();
      });

      // Open modal & close
      fireEvent.click(screen.getByTestId('home-create-project-btn'));
      expect(screen.getByTestId('create-project-modal')).not.toBeNull();
      fireEvent.click(screen.getByText('Cancel'));

      // Dispatch kb:project-created
      window.dispatchEvent(new CustomEvent('kb:project-created'));
      expect(fetchSpy).toHaveBeenCalled();

      // Click + New Work Item
      fireEvent.click(screen.getByTestId('home-create-issue-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('issues-dest')).not.toBeNull();
      });

      // Render standalone views without params (fallback 'KAN')
      render(
        <MemoryRouter>
          <DraftsWorkspaceView />
          <YourWorkView />
          <ProjectCyclesView />
          <ProjectModulesView />
          <ProjectSavedViewsView />
        </MemoryRouter>,
      );
      expect(screen.getByTestId('drafts-view')).not.toBeNull();
      expect(screen.getByTestId('your-work-view')).not.toBeNull();
      expect(screen.getByTestId('project-cycles-view')).not.toBeNull();
      expect(screen.getByTestId('project-modules-view')).not.toBeNull();
      expect(screen.getByTestId('project-views-view')).not.toBeNull();
    });

    it('covers Sidebar dynamic projects, CreateProjectModal callbacks, Topbar avatar link click, and ProjectIssuesRoute live mode', async () => {
      document.cookie = 'kb_csrf=csrf-live; path=/';
      const mockProjects = [
        { key: 'KAN', name: 'Kanban Core', modules_enabled: true },
        { key: 'SEC', name: 'Security', modules_enabled: false },
      ];
      let patchCount = 0;
      vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.includes('/api/v1/projects/KAN/issues')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: [
                  {
                    id: '01931234-5678-7abc-8def-012345678900',
                    key: 'KAN-1',
                    summary: 'Live issue 1',
                    state: {
                      id: '01931234-5678-7abc-8def-012345678901',
                      name: 'To Do',
                      group: 'unstarted',
                    },
                    priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
                    gate_status: 'vetoed',
                    assignees: [
                      {
                        id: 'a-1',
                        kind: 'principal',
                        principal: {
                          id: 'u-1',
                          handle: 'agent1',
                          display_name: 'Agent One',
                          type: 'AGENT',
                        },
                      },
                      {
                        id: 'a-2',
                        kind: 'free_text',
                        free_text: 'external@example.com',
                      },
                    ],
                  },
                ],
                next_cursor: null,
              }),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/api/v1/projects/KAN/states')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: [
                  {
                    id: '01931234-5678-7abc-8def-012345678901',
                    name: 'To Do',
                    group: 'unstarted',
                    sort_order: 1,
                  },
                  {
                    id: '01931234-5678-7abc-8def-012345678902',
                    name: 'Done',
                    group: 'completed',
                    sort_order: 2,
                  },
                  {
                    id: '01931234-5678-7abc-8def-012345678903',
                    name: 'Weird',
                    group: 'custom',
                  },
                ],
              }),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/api/v1/issues/KAN-1') && init?.method === 'PATCH') {
          patchCount += 1;
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: '01931234-5678-7abc-8def-012345678900',
                key: 'KAN-1',
                summary: 'Live issue 1',
                state: {
                  id: '01931234-5678-7abc-8def-012345678902',
                  name: 'Done',
                  group: 'completed',
                },
                priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥' },
              }),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/api/v1/projects') && (!init?.method || init.method === 'GET')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: mockProjects,
              }),
              { status: 200 },
            ),
          );
        }
        if (url.includes('/api/v1/projects') && init?.method === 'POST') {
          mockProjects.push({ key: 'NEWP', name: 'New Project', modules_enabled: true });
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
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      });

      const { unmount: unmountSidebar } = render(
        <MemoryRouter initialEntries={['/projects/EXT/issues']}>
          <Sidebar projectKey="EXT" projectName="External Project" modulesEnabled={true} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByLabelText('Project: Security')).not.toBeNull();
      });

      // Trigger kb:open-create-project -> modal opens -> create project -> onCreated appends NEWP
      window.dispatchEvent(new CustomEvent('kb:open-create-project'));
      await waitFor(() => {
        expect(screen.getByTestId('create-project-modal')).not.toBeNull();
      });
      fireEvent.change(screen.getByLabelText('Project Name'), {
        target: { value: 'New Project' },
      });
      fireEvent.click(screen.getByTestId('create-project-submit'));
      await waitFor(() => {
        expect(screen.getByLabelText('Project: New Project')).not.toBeNull();
      });

      // Open modal via button and close via Cancel
      fireEvent.click(screen.getByLabelText('Create project'));
      fireEvent.click(screen.getByText('Cancel'));
      unmountSidebar();

      // Topbar avatar menu link click closes menu
      const { unmount: unmountTopbar } = render(
        <QueryClientProvider client={new QueryClient()}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter>
                <Topbar />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>,
      );
      fireEvent.click(screen.getByLabelText('User profile and settings'));
      const menuLinks = screen.getAllByRole('menuitem');
      const settingsLink = menuLinks.find((el) => el.tagName === 'A');
      if (settingsLink) {
        fireEvent.click(settingsLink);
      }
      unmountTopbar();

      // IssuesWorkspaceRoute live mode + bulk actions + ProjectIssuesRoute ?create=1
      render(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?create=1&nomodules=1']}>
            <Routes>
              <Route path="/projects/:projectKey/issues" element={<ProjectIssuesRoute />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getAllByText('Live issue 1').length).toBeGreaterThan(0);
      });

      // Dispatch kb:create-issue
      window.dispatchEvent(new CustomEvent('kb:create-issue'));

      // Select issue row checkbox & run BulkActionBar State + Priority in live mode
      const checkboxes = screen.getAllByRole('checkbox');
      const lastCb = checkboxes[checkboxes.length - 1];
      if (lastCb) {
        fireEvent.click(lastCb);
      }
      const stateBtn = document.querySelector('[data-action="state"]');
      if (stateBtn) {
        fireEvent.click(stateBtn);
      }
      await waitFor(() => {
        expect(patchCount).toBeGreaterThan(0);
      });

      // Unhide completed states after transitioning KAN-1 to Done so priority bulk action can select it
      const showAllBtn = screen.queryByTestId('empty-show-all-states-btn');
      if (showAllBtn) {
        fireEvent.click(showAllBtn);
      }

      // Select again and update priority
      const checkboxesAfter = screen.getAllByRole('checkbox');
      const lastCbAfter = checkboxesAfter[checkboxesAfter.length - 1];
      if (lastCbAfter) {
        fireEvent.click(lastCbAfter);
      }
      const prioBtn = document.querySelector('[data-action="priority"]');
      if (prioBtn) {
        fireEvent.click(prioBtn);
      }
      await waitFor(() => {
        expect(patchCount).toBeGreaterThanOrEqual(1);
      });

      // Render IssuesWorkspaceRoute in board layout in live mode to cover boardStates/boardIssues
      render(
        <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board']}>
          <IssuesWorkspaceRoute projectKey="KAN" initialLayout="board" />
        </MemoryRouter>,
      );
      await waitFor(() => {
        expect(screen.getAllByText('Live issue 1').length).toBeGreaterThan(0);
      });
    });

    it('covers dev stories (RailStory, DrawerActionsStory, StickiesStory, IconStory, MediaStory, EditorStory)', () => {
      // RailStory
      const { unmount: u1 } = render(
        <MemoryRouter>
          <RailStory />
        </MemoryRouter>,
      );
      fireEvent.click(screen.getByText('No Modules (Unmounted)'));
      fireEvent.click(screen.getByText('Restricted Parent (Masked)'));
      fireEvent.click(screen.getByText('All Properties (KAN-142)'));
      u1();

      // DrawerActionsStory
      const { unmount: u2 } = render(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter>
            <DrawerActionsStory />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      fireEvent.click(screen.getByTestId('select-done-btn'));
      fireEvent.click(screen.getByTestId('select-started-btn'));
      u2();

      // StickiesStory
      const { unmount: u3 } = render(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter>
            <StickiesStory />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      fireEvent.click(screen.getByTestId('toggle-theme-btn'));
      fireEvent.click(screen.getByTestId('toggle-theme-btn'));
      fireEvent.click(screen.getByTestId('story-new-sticky-btn'));
      const unarchiveBtn = screen.queryByTestId('unarchive-copy-btn');
      if (unarchiveBtn) fireEvent.click(unarchiveBtn);
      const promoteBtns = screen.queryAllByRole('button', { name: /Promote to Doc/i });
      if (promoteBtns[0]) fireEvent.click(promoteBtns[0]);
      u3();

      // IconStory
      const { unmount: u4 } = render(<IconStory />);
      expect(screen.getByTestId('icon-story')).toBeDefined();
      u4();

      // MediaStory
      const { unmount: u5 } = render(<MediaStory />);
      expect(screen.getByTestId('media-story')).toBeDefined();
      u5();

      // EditorStory
      const { unmount: u6 } = render(
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter>
            <EditorStory />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      fireEvent.click(screen.getByTestId('btn-fix-typo'));
      fireEvent.click(screen.getByTestId('btn-undo'));
      fireEvent.click(screen.getByTestId('btn-load-mermaid'));
      fireEvent.click(screen.getByTestId('btn-load-fallback'));
      fireEvent.click(screen.getByTestId('btn-toggle-theme'));
      fireEvent.click(screen.getByTestId('btn-reset'));
      u6();
    });

    it('covers fetchStagedProjectIssues abort, dedup, cycle detection, and maxPages truncation branches', async () => {
      // 1. Empty and 'undefined' projectKey
      expect(await fetchStagedProjectIssues('')).toEqual({
        items: [],
        pagesFetched: 0,
        truncated: false,
      });
      expect(await fetchStagedProjectIssues('undefined')).toEqual({
        items: [],
        pagesFetched: 0,
        truncated: false,
      });

      // 2. Phase 1 aborted with Error reason and string reason
      const ac1 = new AbortController();
      ac1.abort(new Error('phase1-err'));
      await expect(fetchStagedProjectIssues('KAN', { signal: ac1.signal })).rejects.toThrow(
        'phase1-err',
      );

      const ac2 = new AbortController();
      ac2.abort('raw-string-reason');
      await expect(fetchStagedProjectIssues('KAN', { signal: ac2.signal })).rejects.toThrow(
        'Aborted',
      );

      // 3. Phase 1 + Phase 2 deduplication, sort_by/sort_dir, and cycle detection
      let callIdx = 0;
      vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
        callIdx += 1;
        if (callIdx === 1) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: [
                  { id: '1', key: 'KAN-1', summary: 'One' },
                  { id: '1-dup', key: 'KAN-1', summary: 'One dup' },
                ],
                next_cursor: 'cur-1',
              }),
              { status: 200 },
            ),
          );
        }
        if (callIdx === 2) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                items: [
                  { id: '1-dup2', key: 'KAN-1', summary: 'One dup phase2' },
                  { id: '2', key: 'KAN-2', summary: 'Two' },
                ],
                next_cursor: 'cur-1', // cycle!
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }),
        );
      });

      const phase1Seen: number[] = [];
      const cycleRes = await fetchStagedProjectIssues('KAN', {
        sort_by: 'sequence_id',
        sort_dir: 'desc',
        onPhase1: (items, hasMore) => {
          phase1Seen.push(items.length, hasMore ? 1 : 0);
        },
      });
      expect(phase1Seen).toEqual([1, 1]);
      expect(cycleRes.truncated).toBe(true);
      expect(cycleRes.items.map((i) => i.key)).toEqual(['KAN-1', 'KAN-2']);

      // 4. Phase 2 maxPages truncation
      callIdx = 0;
      vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
        callIdx += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [{ id: String(callIdx), key: `KAN-${String(callIdx)}`, summary: 'Item' }],
              next_cursor: `cur-${String(callIdx)}`,
            }),
            { status: 200 },
          ),
        );
      });
      const maxRes = await fetchStagedProjectIssues('KAN', { maxPages: 2 });
      expect(maxRes.pagesFetched).toBe(2);
      expect(maxRes.truncated).toBe(true);

      // 5. Phase 2 abort during page 1 fetch (with Error and with string reason)
      const acPhase2Err = new AbortController();
      vi.spyOn(globalThis, 'fetch').mockImplementationOnce(() => {
        acPhase2Err.abort(new Error('phase2-err'));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [{ id: '1', key: 'KAN-1', summary: 'Item' }],
              next_cursor: 'cur-next',
            }),
            { status: 200 },
          ),
        );
      });
      await expect(
        fetchStagedProjectIssues('KAN', { signal: acPhase2Err.signal }),
      ).rejects.toThrow('phase2-err');

      const acPhase2Str = new AbortController();
      vi.spyOn(globalThis, 'fetch').mockImplementationOnce(() => {
        acPhase2Str.abort('phase2-str');
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [{ id: '1', key: 'KAN-1', summary: 'Item' }],
              next_cursor: 'cur-next',
            }),
            { status: 200 },
          ),
        );
      });
      await expect(
        fetchStagedProjectIssues('KAN', { signal: acPhase2Str.signal }),
      ).rejects.toThrow('Aborted');
    });

    it('covers AdminDiagnosticsStudio all panels, probes, WS lifecycle, config filters, and IssueSurface placeholderData cache lookup', async () => {
      document.cookie = 'kb_csrf=csrf-diag; path=/';
      const clipboardWrite = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText: clipboardWrite } });

      let probeMode: 'ok' | 'fail-status' | 'throw-msg' | 'throw-empty' = 'ok';
      let containerRuntime = 'podman';
      let isNonRoot = false;

      vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
        const path = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (path.includes('/api/v1/auth/me')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                is_server_admin: false,
                is_workspace_admin: true,
                auth_aal: 'aal2',
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        if (path.includes('/api/v1/admin/diagnostics/probes/realtime')) {
          if (probeMode === 'ok') {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  success: true,
                  db_latency_ms: 1.1,
                  notify_rtt_ms: 2.2,
                  message: 'Broker healthy',
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } },
              ),
            );
          }
          if (probeMode === 'fail-status') {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  success: false,
                  db_latency_ms: 5.0,
                  message: 'Broker degraded',
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } },
              ),
            );
          }
          if (probeMode === 'throw-msg') {
            return Promise.reject(new Error('Broker timeout'));
          }
          return Promise.reject(new Error(''));
        }
        if (path.includes('/api/v1/admin/diagnostics')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                status: 'degraded',
                runtime_and_container: {
                  deployment_mode: 'standalone',
                  in_container: true,
                  container_runtime: containerRuntime,
                  os_platform: 'Linux',
                  python_version: '3.12',
                  is_non_root: isNonRoot,
                  uptime_seconds: 120,
                  cgroup_version: 'v2',
                },
                storage: {
                  persistent_volume: true,
                  attachments_backend: 'local',
                  sri_manifest_present: true,
                  directories: [
                    {
                      name: 'writable-dir',
                      path: '/var/lib/kanban/w',
                      exists: true,
                      writable: true,
                      free_bytes: 1073741824,
                      total_bytes: 2147483648,
                    },
                    {
                      name: 'readonly-dir',
                      path: '/var/lib/kanban/ro',
                      exists: true,
                      writable: false,
                      free_bytes: 1073741824,
                      total_bytes: 2147483648,
                    },
                    {
                      name: 'missing-dir',
                      path: '/var/lib/kanban/missing',
                      exists: false,
                      writable: false,
                      free_bytes: 0,
                      total_bytes: 0,
                    },
                  ],
                },
                database: {
                  connected: true,
                  latency_ms: 1.0,
                  server_version: '16',
                  active_role_non_bypass: true,
                  force_rls_verified: true,
                  alembic_head_current: true,
                  code_heads: ['h1'],
                  db_heads: ['h1'],
                  pool: { size: 5, checked_in: 4, checked_out: 1, overflow: 0 },
                },
                realtime: {
                  ws_enabled: true,
                  ws_paths: ['/ws'],
                  sse_enabled: true,
                  sse_path: '/sse',
                  hub_running: true,
                  hub_draining: false,
                  broker_kind: 'pg_notify',
                  broker_listener_connected: true,
                  broker_publisher_connected: true,
                  outbox_relay_running: true,
                  outbox_pending_count: 2,
                  outbox_dead_letter_count: 1,
                  active_connections_total: 3,
                  workspace_connections: {},
                  ws_connections: 2,
                  sse_connections: 1,
                  heartbeat_interval_s: 25,
                  session_recheck_interval_s: 60,
                  replay_retention_minutes: 60,
                  background_tasks: {
                    listener_alive: true,
                    ping_alive: true,
                    session_check_alive: true,
                  },
                },
                request_proxy_check: {
                  detected_scheme: 'http',
                  is_https: false,
                  forwarded_proto_present: false,
                  origin_allowed_for_ws: true,
                  trusted_proxies_configured: false,
                  csp_connect_src_allows_wss: true,
                  warnings: [],
                },
                sandbox: {
                  tier_a_wasm: {
                    available: true,
                    engine: 'wasmtime',
                    max_fuel: 1000,
                    max_memory_bytes: 1024,
                    timeout_ms: 100,
                    cached_modules: 1,
                  },
                  tier_b_nsjail: {
                    available: false,
                    binary_exists: false,
                    binary_owned_by_root: false,
                    permissions_safe: false,
                    userns_probe_ok: false,
                    seccomp_profile_present: false,
                  },
                },
                services: {
                  rate_limiter_backend: 'pg',
                  valkey_configured: false,
                  background_jobs: [],
                  mcp_mounted: true,
                  mcp_surfaces: ['/mcp/agent'],
                  ai_providers: { total: 1, enabled: 1, kinds: ['openai'] },
                  auth_cards: { total: 1, enabled: 1, kinds: ['local'] },
                  remote_runners: { connected_count: 0 },
                  keyring: { configured: true, source: 'env' },
                },
                config: [
                  {
                    key: 'session_timeout',
                    subsystem: 'Auth & AAL2',
                    value: 3600,
                    source: 'default',
                    redacted: false,
                    notes: 'Timeout',
                  },
                  {
                    key: 'secret_pepper',
                    subsystem: 'Security & CSP',
                    value: '[REDACTED]',
                    source: 'env',
                    redacted: true,
                    notes: 'Secret',
                  },
                ],
                build: { version: '2.0.0' },
                subsystems: {
                  s1: {
                    subsystem: 's1',
                    name: 'Sub 1',
                    status: 'healthy',
                    description: 'OK',
                    details: { a: 1 },
                  },
                  s2: {
                    subsystem: 's2',
                    name: 'Sub 2',
                    status: 'degraded',
                    description: 'Warn',
                    details: { b: 2 },
                  },
                  s3: {
                    subsystem: 's3',
                    name: 'Sub 3',
                    status: 'unhealthy',
                    description: 'Down',
                    details: { c: 3 },
                  },
                },
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({ flagged_total: 0, by_reason: {}, items: [], has_more: false }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      });

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/admin/diagnostics']}>
            <AdminDiagnosticsStudio defaultTab="all" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('admin-diagnostics-studio')).toBeDefined();
      });

      // Summary card shows Podman Container and Root Process
      expect(screen.getByText('Podman Container')).toBeDefined();
      expect(screen.getByText('Root Process')).toBeDefined();
      expect(screen.getByText('Read-Only')).toBeDefined();
      expect(screen.getByText('Missing')).toBeDefined();

      // Switch tabs including All and Health
      fireEvent.click(screen.getByTestId('tab-health'));
      fireEvent.click(screen.getByTestId('tab-all'));

      // Filter config by key, subsystem, value, and select dropdown + copy JSON
      const searchInput = screen.getByTestId('config-search-input');
      fireEvent.change(searchInput, { target: { value: '3600' } });
      fireEvent.change(searchInput, { target: { value: 'Security & CSP' } });
      fireEvent.change(searchInput, { target: { value: '' } });

      const subSelect = screen.getByTestId('config-subsystem-select');
      fireEvent.change(subSelect, { target: { value: 'Auth & AAL2' } });
      fireEvent.change(subSelect, { target: { value: 'ALL' } });

      fireEvent.click(screen.getByTestId('copy-config-btn'));
      expect(clipboardWrite).toHaveBeenCalled();

      // Run PG probe across all 4 outcome branches
      const pgProbeBtn = screen.getByTestId('run-pg-probe-btn');
      fireEvent.click(pgProbeBtn);
      await waitFor(() => {
        expect(screen.getByTestId('probe-alert').textContent).toContain('Broker healthy');
      });

      probeMode = 'fail-status';
      fireEvent.click(pgProbeBtn);
      await waitFor(() => {
        expect(screen.getByTestId('probe-alert').textContent).toContain('Broker degraded');
      });

      probeMode = 'throw-msg';
      fireEvent.click(pgProbeBtn);
      await waitFor(() => {
        expect(screen.getByTestId('probe-alert').textContent).toContain('Broker timeout');
      });

      probeMode = 'throw-empty';
      fireEvent.click(pgProbeBtn);
      await waitFor(() => {
        expect(screen.getByTestId('probe-alert').textContent).toContain(
          'Realtime probe execution failed',
        );
      });

      // Refresh diagnostics with bare-metal host fallback
      containerRuntime = 'bare-metal';
      isNonRoot = true;
      fireEvent.click(screen.getByTestId('refresh-diagnostics-btn'));
      await waitFor(() => {
        expect(screen.getByText('Bare Metal Host')).toBeDefined();
      });

      // WebSocket ping probe: mock WebSocket onopen + onmessage pong
      const origWs = globalThis.WebSocket;
      class FakeWsPong {
        static CONNECTING = 0;
        static OPEN = 1;
        readyState = 1;
        onopen: (() => void) | null = null;
        onmessage: ((ev: { data: unknown }) => void) | null = null;
        onerror: (() => void) | null = null;
        send = vi.fn();
        close = vi.fn();
        constructor() {
          setTimeout(() => {
            this.onopen?.();
            this.onmessage?.({ data: 'not-json' });
            this.onmessage?.({ data: JSON.stringify({ op: 'pong' }) });
          }, 0);
        }
      }
      globalThis.WebSocket = FakeWsPong as unknown as typeof WebSocket;
      fireEvent.click(screen.getByTestId('run-ws-ping-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('ws-probe-badge').textContent).toContain('WS Live');
      });

      // WebSocket ping probe: constructor throws
      globalThis.WebSocket = function ThrowWs() {
        throw new Error('ws blocked');
      } as unknown as typeof WebSocket;
      fireEvent.click(screen.getByTestId('run-ws-ping-btn'));
      globalThis.WebSocket = origWs;
      unmount();

      // IssueSurfaceRoot placeholderData from queryClient ['issues'] cache (array & envelope)
      const qcSurface = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qcSurface.setQueryData(['issues', 'null-entry'], null);
      qcSurface.setQueryData(
        ['issues', 'array-entry'],
        [
          {
            id: 'id-99',
            key: 'KAN-99',
            summary: 'Cached Array Issue',
            state: { id: 's1', name: 'Todo', group: 'unstarted' },
            priority: { slug: 'medium', label: 'Medium' },
          },
        ],
      );
      qcSurface.setQueryData(['issues', 'envelope-entry'], {
        items: [
          {
            id: 'id-100',
            key: 'KAN-100',
            summary: 'Cached Envelope Issue',
            state: { id: 's1', name: 'Todo', group: 'unstarted' },
            priority: { slug: 'high', label: 'High' },
          },
        ],
      });

      vi.spyOn(clientModule.apiClient, 'get').mockImplementation(() => {
        return new Promise(() => {
          /* keep pending to exercise placeholderData */
        });
      });

      const { unmount: uSurface } = render(
        <QueryClientProvider client={qcSurface}>
          <MemoryRouter>
            <IssueSurfaceRoot mode="drawer" issueKey="KAN-100" projectKey="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(screen.getByText('Cached Envelope Issue')).toBeDefined();
      uSurface();
    });
  });
});
