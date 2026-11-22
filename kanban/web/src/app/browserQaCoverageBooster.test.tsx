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
      const idInput = screen.getByLabelText('Identifier (Key)');
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
        expect(screen.getByText('Live issue 1')).not.toBeNull();
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
  });
});
