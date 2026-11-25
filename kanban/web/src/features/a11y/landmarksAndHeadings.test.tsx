// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Strict Landmark Regions, Heading Hierarchy (h1-h6), and Skip-To-Main Enclosures (KAN-356, WCAG 2.2 AA).
 * Mandates:
 * 1. Exactly 1 active <main id="main"> landmark with tabIndex={-1} and accessible skip-to-content link across all route views.
 * 2. Every <nav> landmark carries an explicit, distinct aria-label or aria-labelledby across all routes.
 * 3. Strictly sequential heading hierarchy (h1 -> h2 -> h3) without skipped levels across Docs, Analytics, and Router views.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../../app/shellPanels';
import { AppShell, computeCurrentSection } from '../../app/AppShell';
import { Breadcrumb } from '../../app/Breadcrumb';
import { DocsCenterPage } from '../docs-center/DocsCenterPage';
import { DocsWorkspaceView } from '../docs/DocsWorkspaceView';
import { FlowAnalyticsPage } from '../analytics/FlowAnalyticsPage';
import { LoginPage } from '../auth/LoginPage';
import { SetupClaimPage } from '../auth/SetupClaimPage';
import { DeviceActivatePage } from '../oauth/DeviceActivatePage';
import {
  RoutePlaceholder,
  NotFoundView,
  DraftsWorkspaceView,
  ProjectCyclesView,
  ProjectModulesView,
} from '../../app/routes';
import * as clientModule from '../../api/client';
import * as docsApiModule from '../docs/docsApi';

vi.mock('../../api/client', () => ({
  registerAal2StepUpHandler: vi.fn(),
  unregisterAal2StepUpHandler: vi.fn(),
  apiFetch: vi.fn().mockImplementation((_method: string, url: unknown) => {
    if (typeof url === 'string' && url.includes('/auth/me')) {
      return Promise.resolve({
        id: 'u-1',
        display_name: 'Lead Architect',
        email: 'lead@example.com',
        handle: 'architect',
        is_server_admin: true,
        is_workspace_admin: true,
      });
    }
    return Promise.resolve(null);
  }),
  apiClient: {
    GET: vi.fn(),
    POST: vi.fn(),
    PUT: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  },
}));

vi.mock('../docs/docsApi', async (importOriginal) => {
  const actual = await importOriginal<typeof docsApiModule>();
  return {
    ...actual,
    ensureDocsCsrfToken: vi.fn().mockResolvedValue('test-csrf-token'),
    fetchDocsTree: vi.fn().mockResolvedValue([
      {
        id: 'p-1',
        title: 'Getting Started Guide',
        slug: 'getting-started',
        depth: 0,
        hasChildren: false,
        expanded: false,
        restricted: false,
        children: [],
      },
    ]),
    fetchPage: vi.fn().mockResolvedValue({
      id: 'p-1',
      title: 'Getting Started Guide',
      slug: 'getting-started',
      body_markdown: '# Getting Started Guide\n\nWelcome to the platform.\n\n## First Steps\n\nFollow these steps.',
      version: 1,
      breadcrumbs: [{ id: 'p-1', title: 'Getting Started Guide', slug: 'getting-started' }],
    }),
  };
});

vi.mock('../auth/useSessionGuard', () => ({
  useSessionGuard: vi.fn().mockReturnValue({
    status: 'authenticated',
    mfaPending: false,
    authenticated: true,
    user: {
      id: 'u-1',
      display_name: 'Lead Architect',
      email: 'lead@example.com',
      handle: 'architect',
      is_server_admin: true,
      is_workspace_admin: true,
    },
    workspaceId: 'ws-main',
  }),
}));

vi.mock('../realtime', () => ({
  useRealtimeSubscription: vi.fn(),
}));

interface HeadingNode {
  tag: string;
  level: number;
  text: string;
}

interface LandmarkScanResult {
  mains: HTMLElement[];
  skipLinks: HTMLAnchorElement[];
  navs: { element: HTMLElement; label: string | null }[];
  headings: HeadingNode[];
  headingViolations: string[];
}

function scanLandmarksAndHierarchy(container: HTMLElement): LandmarkScanResult {
  const allMains = Array.from(container.querySelectorAll<HTMLElement>('main, [role="main"]')).filter((el) => {
    return !el.hasAttribute('inert') && el.getAttribute('aria-hidden') !== 'true';
  });

  const skipLinks = Array.from(container.querySelectorAll<HTMLAnchorElement>('a[href="#main"], a.kb-skip-link'));

  const navElements = Array.from(container.querySelectorAll<HTMLElement>('nav, [role="navigation"]')).filter((el) => {
    return !el.hasAttribute('inert') && el.getAttribute('aria-hidden') !== 'true';
  });

  const navs = navElements.map((nav) => ({
    element: nav,
    label:
      nav.getAttribute('aria-label') ??
      nav.getAttribute('aria-labelledby') ??
      nav.getAttribute('title') ??
      null,
  }));

  const headingEls = Array.from(
    container.querySelectorAll<HTMLElement>('h1, h2, h3, h4, h5, h6, [role="heading"]'),
  ).filter((el) => {
    return !el.hasAttribute('inert') && el.getAttribute('aria-hidden') !== 'true';
  });

  const headings: HeadingNode[] = headingEls.map((h) => {
    const tag = h.tagName.toLowerCase();
    let level = 0;
    if (/^h[1-6]$/.test(tag)) {
      level = parseInt(tag[1] ?? '0', 10);
    } else {
      const ariaLevel = h.getAttribute('aria-level');
      level = ariaLevel ? parseInt(ariaLevel, 10) : 2;
    }
    return {
      tag,
      level,
      text: h.textContent.trim(),
    };
  });

  const headingViolations: string[] = [];
  if (headings.length > 0 && !headings.some((h) => h.level === 1)) {
    headingViolations.push('Missing top-level h1 landmark heading');
  }

  let prevLevel = 0;
  for (const h of headings) {
    if (h.level > 0) {
      if (prevLevel > 0 && h.level > prevLevel + 1) {
        headingViolations.push(
          `Skipped heading level: h${String(h.level)} ("${h.text.slice(0, 30)}") directly follows h${String(prevLevel)}`,
        );
      }
      prevLevel = h.level;
    }
  }

  return {
    mains: allMains,
    skipLinks,
    navs,
    headings,
    headingViolations,
  };
}

describe('Strict Landmark Regions, Heading Hierarchy, and Skip-To-Main Enclosures (KAN-356)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });
    vi.restoreAllMocks();

    Element.prototype.scrollIntoView = vi.fn();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Test Case 1: Strict Landmark Regions and Skip-To-Main Enclosures', () => {
    it('AppShell renders an active <main id="main"> with tabIndex={-1} and a functional skip-to-content link', () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <ThemeProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues']}>
                <AppShell projectKey="KAN" projectName="Core System">
                  <div data-testid="test-content">Workspace issues surface</div>
                </AppShell>
              </MemoryRouter>
            </ThemeProvider>
          </ShellPanelsProvider>
        </QueryClientProvider>,
      );

      const scan = scanLandmarksAndHierarchy(container);
      expect(scan.mains).toHaveLength(1);
      const mainEl = scan.mains[0];
      expect(mainEl).toBeDefined();
      if (mainEl) {
        expect(mainEl.id).toBe('main');
        expect(mainEl.getAttribute('tabindex')).toBe('-1');
      }

      expect(scan.skipLinks.length).toBeGreaterThan(0);
      const skipLink = scan.skipLinks[0];
      expect(skipLink).toBeDefined();
      if (skipLink) {
        expect(skipLink.getAttribute('href')).toBe('#main');
        expect(skipLink.textContent).toMatch(/Skip to content/i);
      }

      const focusSpy = vi.fn();
      if (mainEl) {
        mainEl.focus = focusSpy;
      }
      if (skipLink) {
        fireEvent.click(skipLink);
      }
      expect(focusSpy).toHaveBeenCalled();
    });

    it('AppShell marks <main id="main"> as inert and aria-hidden when mobile sidebar drawer is open', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('1279px'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      window.innerWidth = 800;
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <ThemeProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues']}>
                <AppShell projectKey="KAN" projectName="Core System">
                  <div>Main Canvas Content</div>
                </AppShell>
              </MemoryRouter>
            </ThemeProvider>
          </ShellPanelsProvider>
        </QueryClientProvider>,
      );

      const hamburger = container.querySelector('.kb-topbar-hamburger');
      expect(hamburger).not.toBeNull();
      if (hamburger) {
        fireEvent.click(hamburger);
      }

      const mainEl = container.querySelector('#main');
      expect(mainEl).toBeDefined();
      const isHidden = (mainEl?.hasAttribute('inert') === true) || (mainEl?.getAttribute('aria-hidden') === 'true');
      expect(isHidden).toBe(true);

      const mobileDrawer = container.querySelector('[role="dialog"]');
      expect(mobileDrawer).toBeDefined();
      expect(mobileDrawer?.getAttribute('aria-modal')).toBe('true');
    });

    it('Standalone route views (DocsCenterPage, LoginPage, SetupClaimPage, DeviceActivatePage) declare <main id="main"> and skip link', () => {
      // 1. DocsCenterPage
      const { container: docsContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/docs/home']}>
            <DocsCenterPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const docsScan = scanLandmarksAndHierarchy(docsContainer);
      expect(docsScan.mains).toHaveLength(1);
      expect(docsScan.mains[0]?.id).toBe('main');
      expect(docsScan.skipLinks.length).toBeGreaterThan(0);

      // 2. LoginPage
      const { container: loginContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/login']}>
            <LoginPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const loginScan = scanLandmarksAndHierarchy(loginContainer);
      expect(loginScan.mains).toHaveLength(1);
      expect(loginScan.mains[0]?.id).toBe('main');
      expect(loginScan.skipLinks.length).toBeGreaterThan(0);

      // 3. SetupClaimPage
      const { container: setupContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/setup']}>
            <SetupClaimPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const setupScan = scanLandmarksAndHierarchy(setupContainer);
      expect(setupScan.mains).toHaveLength(1);
      expect(setupScan.mains[0]?.id).toBe('main');
      expect(setupScan.skipLinks.length).toBeGreaterThan(0);

      // 4. DeviceActivatePage
      const { container: deviceContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/activate']}>
            <DeviceActivatePage />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const deviceScan = scanLandmarksAndHierarchy(deviceContainer);
      expect(deviceScan.mains).toHaveLength(1);
      expect(deviceScan.mains[0]?.id).toBe('main');
      expect(deviceScan.skipLinks.length).toBeGreaterThan(0);
    });

    it('computeCurrentSection correctly handles route paths and fallbacks', () => {
      expect(computeCurrentSection('/admin/diagnostics')).toBe('Diagnostics');
      expect(computeCurrentSection('/admin/link-auditor')).toBe('Diagnostics');
      expect(computeCurrentSection('/about')).toBe('About');
      expect(computeCurrentSection('/settings/workflows')).toBe('Workflows');
      expect(computeCurrentSection('/settings/custom-fields')).toBe('Custom Fields');
      expect(computeCurrentSection('/projects/KAN/settings')).toBe('Settings');
      expect(computeCurrentSection('/projects/KAN/cycles')).toBe('Cycles');
      expect(computeCurrentSection('/projects/KAN/modules')).toBe('Modules');
      expect(computeCurrentSection('/projects/KAN/docs')).toBe('Docs');
      expect(computeCurrentSection('/projects/KAN/stickies')).toBe('Stickies');
      expect(computeCurrentSection('/projects/KAN/views')).toBe('Views');
      expect(computeCurrentSection('/projects/KAN/activity')).toBe('Activity');
      expect(computeCurrentSection('/projects/KAN/overview')).toBe('Overview');
      expect(computeCurrentSection('/projects/KAN/issues')).toBe('Work Items');
      expect(computeCurrentSection('/unknown-path', 'Custom Fallback')).toBe('Custom Fallback');
    });
  });

  describe('Test Case 2: Explicit, Distinct Accessible Labels Across All Navigation (<nav>) Landmarks', () => {
    it('100% of <nav> landmarks across AppShell, Sidebar, and Breadcrumb carry distinct explicit accessible names', () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <ThemeProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues']}>
                <AppShell projectKey="KAN" projectName="Core System">
                  <div>
                    <Breadcrumb workspaceName="Enterprise Hub" projectKey="KAN" projectName="Core System" />
                  </div>
                </AppShell>
              </MemoryRouter>
            </ThemeProvider>
          </ShellPanelsProvider>
        </QueryClientProvider>,
      );

      const scan = scanLandmarksAndHierarchy(container);
      expect(scan.navs.length).toBeGreaterThanOrEqual(2);

      for (const nav of scan.navs) {
        expect(nav.label).toBeTruthy();
        expect(nav.label?.trim().length).toBeGreaterThan(0);
      }

      const labels = scan.navs.map((n) => n.label);
      expect(labels).toContain('Workspace navigation');
      expect(labels).toContain('Projects navigation');
      expect(labels).toContain('Breadcrumb');
    });

    it('DocsCenterPage navigation landmarks declare distinct accessible labels (Chapters, Drawer, Pagination)', () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/docs/home']}>
            <DocsCenterPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const openDrawerBtn = screen.getByTestId('docs-mobile-chapters-btn');
      fireEvent.click(openDrawerBtn);

      const scan = scanLandmarksAndHierarchy(container);
      const navLabels = scan.navs.map((n) => n.label);

      expect(navLabels).toContain('Documentation Chapters');
      expect(navLabels).toContain('Mobile Chapters Navigation');
      expect(navLabels).toContain('Chapter Pagination');

      for (const nav of scan.navs) {
        expect(nav.label).not.toBeNull();
        expect(nav.label?.length).toBeGreaterThan(2);
      }
    });
  });

  describe('Test Case 3: Sequential Heading Hierarchy (h1-h6) Without Skipped Levels Across Route Views', () => {
    it('DocsCenterPage enforces an h1 primary heading and strictly sequential subheadings without skipping levels', () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/docs/home']}>
            <DocsCenterPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const scan = scanLandmarksAndHierarchy(container);
      expect(scan.headings.length).toBeGreaterThan(0);
      expect(scan.headings[0]?.level).toBe(1);
      expect(scan.headingViolations).toEqual([]);
    });

    it('DocsWorkspaceView enforces an h1 primary heading and sequential pane headings', () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/docs/p-1']}>
            <Routes>
              <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const scan = scanLandmarksAndHierarchy(container);
      expect(scan.headings.some((h) => h.level === 1)).toBe(true);
      expect(scan.headingViolations).toEqual([]);
    });

    it('FlowAnalyticsPage provides primary h1 and strictly sequential h2 and h3 chart hierarchy', async () => {
      const mockFlowData = {
        project_key: 'KAN',
        project_id: 'a0000000-0000-0000-0000-000000000001',
        window_days: 90,
        cfd: {
          states: [{ id: 's1', name: 'Backlog', state_group: 'backlog', color_hex: '#94a3b8', sort_order: 1 }],
          state_groups: ['backlog'],
          points: [{ date: '2026-11-01', backlog: 5, unstarted: 0, started: 2, completed: 1, cancelled: 0, total: 8 }],
        },
        cycle_lead_time: {
          points: [{ issue_id: 'i1', issue_key: 'KAN-1', title: 'Task 1', cycle_time_days: 2.5, lead_time_days: 5.0, completed_at: '2026-11-02T10:00:00Z' }],
          cycle_time_percentiles: { p50: 2.5, p85: 4.0, p95: 5.0 },
          lead_time_percentiles: { p50: 5.0, p85: 8.0, p95: 10.0 },
          total_completed_in_window: 1,
        },
        aging_wip: {
          active_issues: [],
          column_thresholds: {},
          total_active_wip: 0,
        },
        monte_carlo: {
          average_daily_throughput: 1.5,
          trials_count: 10000,
          how_many: { horizon_days: 14, percentiles: { p50: 20, p85: 15, p95: 10 } },
          when: { target_items: 20, percentiles: { p50: 14, p85: 20, p95: 25 } },
        },
      };

      vi.mocked(clientModule.apiFetch).mockImplementation((_method, url) => {
        if (typeof url === 'string' && url.includes('/analytics/flow')) {
          return Promise.resolve(mockFlowData);
        }
        if (typeof url === 'string' && url.includes('/cycles')) {
          return Promise.resolve([{ id: 'c-1', name: 'Sprint 1', status: 'active' }]);
        }
        return Promise.resolve({});
      });

      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/analytics']}>
            <Routes>
              <Route path="/projects/:projectKey/analytics" element={<FlowAnalyticsPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const h1Title = await screen.findByRole('heading', { level: 1, name: /Flow Telemetry Studio/i });
      expect(h1Title).toBeDefined();

      const scan = scanLandmarksAndHierarchy(container);
      expect(scan.headings.some((h) => h.level === 1)).toBe(true);
      expect(scan.headingViolations).toEqual([]);
    });

    it('ProjectCyclesView, ProjectModulesView, DraftsWorkspaceView, and RoutePlaceholder enforce sequential heading hierarchy', () => {
      // 1. DraftsWorkspaceView
      const { container: draftsContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <DraftsWorkspaceView />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const draftsScan = scanLandmarksAndHierarchy(draftsContainer);
      expect(draftsScan.headings[0]?.level).toBe(1);
      expect(draftsScan.headingViolations).toEqual([]);

      // 2. ProjectCyclesView
      const { container: cyclesContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/cycles']}>
            <Routes>
              <Route path="/projects/:projectKey/cycles" element={<ProjectCyclesView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const cyclesScan = scanLandmarksAndHierarchy(cyclesContainer);
      expect(cyclesScan.headings[0]?.level).toBe(1);
      expect(cyclesScan.headingViolations).toEqual([]);

      // 3. ProjectModulesView
      const { container: modulesContainer } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/modules']}>
            <Routes>
              <Route path="/projects/:projectKey/modules" element={<ProjectModulesView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const modulesScan = scanLandmarksAndHierarchy(modulesContainer);
      expect(modulesScan.headings[0]?.level).toBe(1);
      expect(modulesScan.headingViolations).toEqual([]);

      // 4. RoutePlaceholder
      const { container: placeholderContainer } = render(<RoutePlaceholder route="/test-route" />);
      const placeholderScan = scanLandmarksAndHierarchy(placeholderContainer);
      expect(placeholderScan.headings[0]?.level).toBe(1);
      expect(placeholderScan.headingViolations).toEqual([]);

      // 5. NotFoundView
      const { container: notFoundContainer } = render(
        <MemoryRouter>
          <NotFoundView />
        </MemoryRouter>,
      );
      const notFoundScan = scanLandmarksAndHierarchy(notFoundContainer);
      expect(notFoundScan.headings[0]?.level).toBe(1);
      expect(notFoundScan.headingViolations).toEqual([]);
    });
  });
});
