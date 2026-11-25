/**
 * Breathable Application Shell (KB-P3-34, S6.3).
 * Breathable grid layout hosting collapsible sidebar rail, calm topbar, command palette, and surface anchors.
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
import { Sidebar, SIDEBAR_STORAGE_KEY, sanitizeSidebarState } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette, type CachedIssue } from './CommandPalette';
import { ShortcutsCheatSheetModal } from './ShortcutsCheatSheetModal';
import { GlobalErrorAlertEnhancer } from '../components/help/ErrorHelpHint';
import { registerShellPanel, ShellPanelsProvider } from './shellPanels';
import { registerShortcut } from './shortcuts';
import { RealtimeStatus } from '../api/RealtimeStatus';
import { useRealtimeSubscription } from '../realtime';
import { type AccessManifestData } from './HeaderPills';
import { type SystemStatus } from './useSystemStatus';
import { IssueSurface } from '../features/drawer/IssueSurface';
import { IssueSurfaceSlotsContext } from '../features/drawer/slots';
import { issueSurfaceSlots } from '../features/drawer/slotRegistry';
import { AccessInspectorHost } from '../features/access/useAccessInspector';
import { StandaloneStatusPanel } from '../features/standalone/StandaloneStatusPanel';
import { HelpDrawer } from '../features/docs-center/HelpDrawer';
import { useSessionGuard } from '../features/auth/useSessionGuard';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import { apiFetch } from '../api/client';
import {
  BRAND_TITLE,
  formatDocumentTitle,
  useDocumentTitle,
} from './documentTitle';
import type { TopbarUser } from './Topbar';
import './AppShell.css';

registerShellPanel('standalone', StandaloneStatusPanel);
registerShellPanel('help', HelpDrawer);

export interface AppShellProps {
  children?: ReactNode;
  projectKey?: string | undefined;
  projectId?: string | undefined;
  projectName?: string | undefined;
  modulesEnabled?: boolean | undefined;
  showLayoutSwitcher?: boolean | undefined;
  issueCount?: number | null | undefined;
  currentSection?: string | undefined;
  accessManifest?: AccessManifestData | null | undefined;
  systemStatus?: SystemStatus | null | undefined;
  cachedIssues?: readonly CachedIssue[] | undefined;
}

export function computeCurrentSection(pathname: string, fallback = 'Work Items'): string {
  if (pathname.includes('/admin/imports')) {
    return 'Migration Import Studio';
  }
  if (pathname.includes('/admin/auth')) {
    return 'Auth Cards';
  }
  if (pathname.includes('/admin/oauth')) {
    return 'OAuth Clients';
  }
  if (pathname.includes('/admin/agent-runners')) {
    return 'Agent Runners';
  }
  if (pathname.includes('/admin/ai')) {
    return 'AI Providers';
  }
  if (pathname.includes('/admin/agents')) {
    return 'Autonomous Agents';
  }
  if (pathname.includes('/admin/diagnostics') || pathname.includes('/admin/link-auditor')) {
    return 'Diagnostics';
  }
  if (pathname === '/about' || pathname.startsWith('/about') || pathname.includes('/about')) {
    return 'About';
  }
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
  showLayoutSwitcher,
  issueCount,
  currentSection = 'Work Items',
  accessManifest,
  systemStatus,
  cachedIssues,
}: AppShellProps): JSX.Element {
  const sessionGuard = useSessionGuard();
  const isAuthReady =
    sessionGuard.status === 'authenticated' &&
    !sessionGuard.mfaPending &&
    sessionGuard.authenticated !== false;

  const location = useLocation();
  const navigate = useNavigate();
  const match = /\/projects\/([^/]+)/.exec(location.pathname);
  const activeProjectKey = match?.[1] ?? projectKey;
  useRealtimeSubscription([
    isAuthReady && activeProjectKey ? `project:${activeProjectKey}` : null,
    isAuthReady && projectId ? `project:${projectId}` : null,
    isAuthReady && sessionGuard.workspaceId ? `workspace:${sessionGuard.workspaceId}` : null,
  ]);
  const isInsideProject = Boolean(match) || (Boolean(activeProjectKey) && location.pathname.startsWith('/projects'));
  const computedSection =
    currentSection && currentSection !== 'Work Items'
      ? currentSection
      : computeCurrentSection(location.pathname, currentSection);

  const isProjectIssuesRoute = /^(?:\/projects|\/w\/[^/]+\/p)\/[^/]+\/issues(?:\/)?$/.test(location.pathname);
  const searchParams = new URLSearchParams(location.search);
  const rawLayout = searchParams.get('layout');
  const isListSplitHandled = isProjectIssuesRoute && (!rawLayout || rawLayout.toLowerCase() === 'list');

  const isPublicRoute =
    location.pathname.startsWith('/login') ||
    location.pathname.startsWith('/setup') ||
    location.pathname.startsWith('/activate');

  const shellTitle =
    location.pathname === '/'
      ? BRAND_TITLE
      : formatDocumentTitle(
          isInsideProject && projectName && projectName.toLowerCase() !== BRAND_TITLE.toLowerCase()
            ? [computedSection, projectName]
            : [computedSection],
        );
  useDocumentTitle(shellTitle);

  const meQuery = useQuery<TopbarUser | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as TopbarUser;
      } catch {
        return null;
      }
    },
    enabled: !isPublicRoute && isAuthReady,
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

  // Auto-close mobile sidebar on navigation
  const currentLoc = location.pathname + location.search;
  const [prevLocation, setPrevLocation] = useState(currentLoc);
  if (prevLocation !== currentLoc) {
    setPrevLocation(currentLoc);
    setMobileSidebarOpen(false);
  }

  // Auto-close mobile sidebar when viewport expands past 1280px
  useEffect(() => {
    function handleResize(): void {
      if (window.innerWidth > 1279) {
        setMobileSidebarOpen(false);
      }
    }
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
      return sanitizeSidebarState(stored) === 'collapsed';
    /* v8 ignore start */
    } catch {
      return false;
    }
    /* v8 ignore stop */
  });

  const toggleSidebarCollapse = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  useEffect(() => {
    try {
      const stateStr = isSidebarCollapsed ? 'collapsed' : 'open';
      localStorage.setItem(SIDEBAR_STORAGE_KEY, stateStr);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('kb:sidebar-changed', {
            detail: { collapsed: stateStr },
          }),
        );
      }
    } catch {
      // Ignore storage errors
    }
  }, [isSidebarCollapsed]);

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsModalOpen, setShortcutsModalOpen] = useState(false);
  const hamburgerButtonRef = useRef<HTMLButtonElement | null>(null);

  const handleToggleSidebar = useCallback(() => {
    if (typeof window !== 'undefined' && window.innerWidth <= 1279) {
      setMobileSidebarOpen((prev) => !prev);
    } else {
      toggleSidebarCollapse();
    }
  }, [toggleSidebarCollapse]);

  // Register global shortcuts: Mod+K, [, C, ?
  useEffect(() => {
    const unregisterModK = registerShortcut(
      'Mod+K',
      (e) => {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      },
      { allowInInputs: true },
    );

    const unregisterSidebar = registerShortcut(
      '[',
      (e) => {
        e.preventDefault();
        toggleSidebarCollapse();
      },
      { allowInInputs: false },
    );

    const unregisterCreate = registerShortcut(
      'C',
      (e) => {
        e.preventDefault();
        window.dispatchEvent(
          new CustomEvent('kb:create-issue', { bubbles: true }),
        );
      },
      { allowInInputs: false },
    );

    const unregisterCheat = registerShortcut(
      '?',
      (e) => {
        e.preventDefault();
        setShortcutsModalOpen(true);
      },
      { allowInInputs: false },
    );

    const handleOpenShortcuts = (): void => {
      setShortcutsModalOpen(true);
    };
    window.addEventListener('kb:open-shortcuts', handleOpenShortcuts);

    return () => {
      unregisterModK();
      unregisterSidebar();
      unregisterCreate();
      unregisterCheat();
      window.removeEventListener('kb:open-shortcuts', handleOpenShortcuts);
    };
  }, [toggleSidebarCollapse]);

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

  if (!isAuthReady) {
    return (
      <div className="kb-app-shell" data-testid="app-shell-auth-loading">
        <main id="main" tabIndex={-1} className="kb-main-canvas" aria-label="Loading workspace" />
      </div>
    );
  }

  return (
    <ShellPanelsProvider>
      <div className={`kb-app-shell ${isSidebarCollapsed ? 'kb-app-shell--sidebar-collapsed' : ''}`}>
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
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={toggleSidebarCollapse}
          projectKey={isInsideProject ? activeProjectKey : undefined}
          projectName={isInsideProject ? projectName : undefined}
          modulesEnabled={modulesEnabled}
          triggerButtonRef={hamburgerButtonRef}
          user={currentUser}
        />

        {/* 52px Uncluttered Topbar Header */}
        <Topbar
          isSidebarOpen={mobileSidebarOpen}
          isSidebarCollapsed={isSidebarCollapsed}
          onToggleSidebar={toggleMobileSidebar}
          onToggleCollapse={toggleSidebarCollapse}
          onOpenPalette={() => { setPaletteOpen(true); }}
          workspaceName={isInsideProject ? 'kanban' : undefined}
          projectKey={isInsideProject ? activeProjectKey : undefined}
          projectId={isInsideProject ? (projectId ?? activeProjectKey) : undefined}
          projectName={isInsideProject ? projectName : undefined}
          currentSection={computedSection}
          issueCount={issueCount}
          accessManifest={accessManifest}
          systemStatus={systemStatus}
          showLayoutSwitcher={showLayoutSwitcher}
          user={currentUser}
          hamburgerButtonRef={hamburgerButtonRef}
        />

        {/* Main Canvas Region */}
        <main
          id="main"
          tabIndex={-1}
          className="kb-main-canvas"
          inert={mobileSidebarOpen ? true : undefined}
          aria-hidden={mobileSidebarOpen ? 'true' : undefined}
        >
          {children ?? <Outlet />}
        </main>

        {/* Stable Surface Host Anchor for KB-P3-41 Drawer */}
        <div id="kb-surface-host">
          <div id="kb-issue-surface-host">
            <IssueSurfaceSlotsContext.Provider value={issueSurfaceSlots}>
              {!isListSplitHandled && <IssueSurface />}
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
          onToggleSidebar={handleToggleSidebar}
          projectKey={projectKey}
          cachedIssues={cachedIssues}
          user={currentUser}
        />

        {/* Global Keyboard Shortcuts Cheat Sheet Modal */}
        <ShortcutsCheatSheetModal
          isOpen={shortcutsModalOpen}
          onClose={() => { setShortcutsModalOpen(false); }}
        />

        {/* Global Error Alert Enhancer & AAL2 Step-Up Host (KAN-393) */}
        <GlobalErrorAlertEnhancer />
      </div>
    </ShellPanelsProvider>
  );
}
