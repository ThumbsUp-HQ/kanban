/**
 * Breathable Application Shell (KB-P3-34, S6.3).
 * Plane-parity grid layout hosting collapsible sidebar rail, calm topbar, command palette, and surface anchors.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette, type CachedIssue } from './CommandPalette';
import { registerShellPanel, ShellPanelsProvider } from './shellPanels';
import { registerShortcut } from './shortcuts';
import { RealtimeStatus } from '../api/RealtimeStatus';
import { type AccessManifestData } from './HeaderPills';
import { type SystemStatus } from './useSystemStatus';
import { IssueSurface } from '../features/drawer/IssueSurface';
import { IssueSurfaceSlotsContext } from '../features/drawer/slots';
import { issueSurfaceSlots } from '../features/drawer/slotRegistry';
import { AccessInspectorHost } from '../features/access/useAccessInspector';
import { StandaloneStatusPanel } from '../features/standalone/StandaloneStatusPanel';
import { useSessionGuard } from '../features/auth/useSessionGuard';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import { apiFetch } from '../api/client';
import type { TopbarUser } from './Topbar';
import './AppShell.css';

registerShellPanel('standalone', StandaloneStatusPanel);

export interface AppShellProps {
  children?: ReactNode;
  projectKey?: string | undefined;
  projectId?: string | undefined;
  projectName?: string | undefined;
  modulesEnabled?: boolean | undefined;
  issueCount?: number | null | undefined;
  currentSection?: string | undefined;
  accessManifest?: AccessManifestData | null | undefined;
  systemStatus?: SystemStatus | null | undefined;
  cachedIssues?: readonly CachedIssue[] | undefined;
}

export function computeCurrentSection(pathname: string, fallback = 'Work Items'): string {
  if (pathname.includes('/settings/workflows') || pathname.endsWith('/workflows')) {
    return 'Workflows';
  }
  if (pathname.includes('/settings/custom-fields')) {
    return 'Custom Fields';
  }
  if (pathname.includes('/settings')) {
    return 'Settings';
  }
  if (pathname.includes('/cycles')) {
    return 'Cycles';
  }
  if (pathname.includes('/modules')) {
    return 'Modules';
  }
  if (pathname.includes('/docs')) {
    return 'Docs';
  }
  if (pathname.includes('/stickies')) {
    return 'Stickies';
  }
  if (pathname.includes('/views')) {
    return 'Views';
  }
  if (pathname.includes('/activity')) {
    return 'Activity';
  }
  if (pathname.includes('/overview')) {
    return 'Overview';
  }
  if (pathname.includes('/issues')) {
    return 'Work Items';
  }
  return fallback;
}

export function AppShell({
  children,
  projectKey,
  projectId,
  projectName,
  modulesEnabled = true,
  issueCount,
  currentSection = 'Work Items',
  accessManifest,
  systemStatus,
  cachedIssues,
}: AppShellProps): JSX.Element {
  useSessionGuard();
  const location = useLocation();
  const navigate = useNavigate();
  const match = /\/projects\/([^/]+)/.exec(location.pathname);
  const activeProjectKey = match?.[1] ?? projectKey;
  const isInsideProject = Boolean(match) || (Boolean(activeProjectKey) && location.pathname.startsWith('/projects'));
  const computedSection =
    currentSection && currentSection !== 'Work Items'
      ? currentSection
      : computeCurrentSection(location.pathname, currentSection);

  const isPublicRoute =
    location.pathname.startsWith('/login') ||
    location.pathname.startsWith('/setup') ||
    location.pathname.startsWith('/activate');

  const meQuery = useQuery<TopbarUser | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as TopbarUser;
      } catch {
        return null;
      }
    },
    enabled: !isPublicRoute,
    staleTime: 60000,
  });

  const currentUser = meQuery.data ?? null;

  useEffect(() => {
    function handleManageAccess(e: Event): void {
      const customEv = e as CustomEvent<{ objectId?: string; projectKey?: string }>;
      const targetProjKey = customEv.detail.projectKey ?? activeProjectKey;
      if (targetProjKey) {
        void navigate(`/projects/${targetProjKey}/settings`);
      } else {
        void navigate('/workspaces/settings');
      }
    }
    window.addEventListener('kb:open-manage-access', handleManageAccess);
    return () => {
      window.removeEventListener('kb:open-manage-access', handleManageAccess);
    };
  }, [activeProjectKey, navigate]);

  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const hamburgerButtonRef = useRef<HTMLButtonElement | null>(null);

  // Register Cmd/Ctrl+K shortcut (allowed even inside inputs)
  useEffect(() => {
    const unregister = registerShortcut(
      'Mod+K',
      (e) => {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      },
      { allowInInputs: true },
    );
    return unregister;
  }, []);

  const toggleMobileSidebar = useCallback(() => {
    setMobileSidebarOpen((prev) => !prev);
  }, []);

  const handleSkipClick = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    e.preventDefault();
    const mainEl = document.getElementById('main') ?? document.getElementById('kb-main');
    if (mainEl) {
      mainEl.focus();
    }
  };

  return (
    <ShellPanelsProvider>
      <div className="kb-app-shell">
        {/* Skip to Content Link (A11y) */}
        <a
          href="#main"
          className="kb-skip-link"
          onClick={handleSkipClick}
        >
          Skip to content
        </a>

        {/* 256px Collapsible Sidebar Navigation Rail */}
        <Sidebar
          isOpen={mobileSidebarOpen}
          onClose={() => { setMobileSidebarOpen(false); }}
          projectKey={isInsideProject ? activeProjectKey : undefined}
          projectName={isInsideProject ? projectName : undefined}
          modulesEnabled={modulesEnabled}
          triggerButtonRef={hamburgerButtonRef}
          user={currentUser}
        />

        {/* 52px Uncluttered Topbar Header */}
        <Topbar
          isSidebarOpen={mobileSidebarOpen}
          onToggleSidebar={toggleMobileSidebar}
          onOpenPalette={() => { setPaletteOpen(true); }}
          workspaceName={isInsideProject ? 'kanban' : undefined}
          projectKey={isInsideProject ? activeProjectKey : undefined}
          projectId={isInsideProject ? (projectId ?? activeProjectKey) : undefined}
          projectName={isInsideProject ? projectName : undefined}
          currentSection={computedSection}
          issueCount={issueCount}
          accessManifest={accessManifest}
          systemStatus={systemStatus}
          showLayoutSwitcher={false}
          user={currentUser}
        />

        {/* Main Canvas Region */}
        <main id="main" tabIndex={-1} className="kb-main-canvas">
          {children ?? <Outlet />}
        </main>

        {/* Stable Surface Host Anchor for KB-P3-41 Drawer */}
        <div id="kb-surface-host">
          <div id="kb-issue-surface-host">
            <IssueSurfaceSlotsContext.Provider value={issueSurfaceSlots}>
              <IssueSurface />
            </IssueSurfaceSlotsContext.Provider>
          </div>
        </div>

        {/* Stable Semantic Emoji Hint Portal Anchor for KB-P3-31 */}
        <div id="kb-hint-root" />

        {/* Global Effective Access Inspector Popover Host (KB-P3-49) */}
        <AccessInspectorHost />

        {/* Non-blocking Realtime Network & SSE Status Chip */}
        <RealtimeStatus />

        {/* Accessible Fuzzy Command Palette Dialog */}
        <CommandPalette
          isOpen={paletteOpen}
          onClose={() => { setPaletteOpen(false); }}
          onToggleSidebar={toggleMobileSidebar}
          projectKey={projectKey}
          cachedIssues={cachedIssues}
          user={currentUser}
        />
      </div>
    </ShellPanelsProvider>
  );
}
