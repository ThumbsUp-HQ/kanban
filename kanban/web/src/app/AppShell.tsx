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
import { Outlet } from 'react-router';
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
import './AppShell.css';

registerShellPanel('standalone', StandaloneStatusPanel);

export interface AppShellProps {
  children?: ReactNode;
  projectKey?: string | undefined;
  projectName?: string | undefined;
  modulesEnabled?: boolean | undefined;
  issueCount?: number | null | undefined;
  currentSection?: string | undefined;
  accessManifest?: AccessManifestData | null | undefined;
  systemStatus?: SystemStatus | null | undefined;
  cachedIssues?: readonly CachedIssue[] | undefined;
}

export function AppShell({
  children,
  projectKey = 'KAN',
  projectName = 'kanban',
  modulesEnabled = true,
  issueCount,
  currentSection = 'Work Items',
  accessManifest,
  systemStatus,
  cachedIssues,
}: AppShellProps): JSX.Element {
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
          projectKey={projectKey}
          projectName={projectName}
          modulesEnabled={modulesEnabled}
          triggerButtonRef={hamburgerButtonRef}
        />

        {/* 52px Uncluttered Topbar Header */}
        <Topbar
          isSidebarOpen={mobileSidebarOpen}
          onToggleSidebar={toggleMobileSidebar}
          onOpenPalette={() => { setPaletteOpen(true); }}
          projectKey={projectKey}
          projectName={projectName}
          currentSection={currentSection}
          issueCount={issueCount}
          accessManifest={accessManifest}
          systemStatus={systemStatus}
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
        />
      </div>
    </ShellPanelsProvider>
  );
}
