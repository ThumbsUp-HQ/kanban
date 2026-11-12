/**
 * Sidebar Navigation Rail (KB-P3-34, S6.3).
 * 256px collapsible navigation rail with Plane parity, [👍] 👍kanban branding, and accessible keyboard focus trapping.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { NavLink, useLocation } from 'react-router';
import { registerShortcut } from './shortcuts';
import './Sidebar.css';

export interface ProjectNavData {
  key: string;
  name: string;
  modules_enabled?: boolean;
}

export interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
  onToggleCollapse?: () => void;
  projectKey?: string;
  projectName?: string;
  modulesEnabled?: boolean;
  activePath?: string;
  triggerButtonRef?: React.RefObject<HTMLButtonElement | null>;
}

export const SIDEBAR_STORAGE_KEY = 'kb.sidebar';

export function sanitizeSidebarState(value: string | null): 'open' | 'collapsed' {
  if (value === 'open' || value === 'collapsed') {
    return value;
  }
  return 'open';
}

export function Sidebar({
  isOpen = true,
  onClose,
  onToggleCollapse,
  projectKey = 'KAN',
  projectName = 'kanban',
  modulesEnabled = true,
  activePath: activePathProp,
  triggerButtonRef,
}: SidebarProps): JSX.Element {
  let locationPathname = '';
  try {
    const loc = useLocation();
    locationPathname = loc.pathname;
  } catch {
    // Outside Router
  }

  const currentPath = activePathProp ?? locationPathname;

  // Stored desktop collapse state
  const [collapsed, setCollapsed] = useState<'open' | 'collapsed'>(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY);
      return sanitizeSidebarState(stored);
    } catch {
      return 'open';
    }
  });

  const [projectExpanded, setProjectExpanded] = useState(true);
  const sidebarRef = useRef<HTMLElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);

  // Toggle desktop collapsed state
  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = prev === 'open' ? 'collapsed' : 'open';
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, next);
      } catch {
        // Ignore storage errors
      }
      return next;
    });
    onToggleCollapse?.();
  }, [onToggleCollapse]);

  // Register '[' shortcut to toggle sidebar collapse
  useEffect(() => {
    const unregister = registerShortcut('[', () => {
      toggleCollapsed();
    });
    return unregister;
  }, [toggleCollapsed]);

  // Mobile overlay focus trap and Escape handler
  useEffect(() => {
    if (!isOpen) return;

    // Focus first focusable item on mobile open
    const timer = setTimeout(() => {
      firstItemRef.current?.focus();
    }, 0);

    return () => { clearTimeout(timer); };
  }, [isOpen]);

  const handleMobileKeyDown = (e: KeyboardEvent<HTMLElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose?.();
      triggerButtonRef?.current?.focus();
      return;
    }

    if (e.key === 'Tab' && sidebarRef.current) {
      const focusables = sidebarRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (first && last) {
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  };

  const handleCreateIssue = (): void => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('kb:create-issue', { bubbles: true }),
      );
    }
  };

  const isDesktopCollapsed = collapsed === 'collapsed';

  return (
    <>
      {/* Mobile Backdrop Scrim */}
      <div
        className={`kb-sidebar-scrim ${isOpen ? 'kb-sidebar-scrim-active' : ''}`}
        onClick={() => {
          onClose?.();
          triggerButtonRef?.current?.focus();
        }}
      />

      <aside
        ref={sidebarRef}
        role={isOpen && typeof window !== 'undefined' && window.innerWidth <= 1279 ? 'dialog' : undefined}
        aria-modal={isOpen && typeof window !== 'undefined' && window.innerWidth <= 1279 ? 'true' : undefined}
        aria-label="Sidebar navigation"
        className={`kb-sidebar ${isDesktopCollapsed ? 'kb-sidebar-collapsed' : ''} ${
          isOpen ? 'kb-sidebar-overlay' : ''
        }`}
        onKeyDown={handleMobileKeyDown}
      >
        {/* Workspace Brand & New Item Button */}
        <div className="kb-sidebar-header">
          <button
            ref={firstItemRef}
            type="button"
            className="kb-workspace-switcher"
            aria-label="Workspace switcher: [👍] 👍kanban"
          >
            <span className="kb-workspace-brand">
              <span aria-hidden="true">[👍]</span>
              <span>👍kanban</span>
            </span>
            <span aria-hidden="true">▾</span>
          </button>

          <button
            type="button"
            className="kb-new-item-btn"
            onClick={handleCreateIssue}
          >
            <span aria-hidden="true">+</span>
            <span>New work item</span>
          </button>
        </div>

        {/* Workspace Section */}
        <div className="kb-sidebar-section">
          <div className="kb-sidebar-heading">Workspace</div>
          <nav aria-label="Workspace navigation">
            <ul className="kb-sidebar-nav-list">
              <li>
                <NavLink
                  to="/"
                  className="kb-sidebar-nav-item"
                  aria-current={currentPath === '/' ? 'page' : undefined}
                >
                  <span className="kb-sidebar-icon" aria-hidden="true">
                    🏠
                  </span>
                  <span>Home</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/drafts"
                  className="kb-sidebar-nav-item"
                  aria-current={currentPath === '/drafts' ? 'page' : undefined}
                >
                  <span className="kb-sidebar-icon" aria-hidden="true">
                    📝
                  </span>
                  <span>Drafts</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/your-work"
                  className="kb-sidebar-nav-item"
                  aria-current={currentPath === '/your-work' ? 'page' : undefined}
                >
                  <span className="kb-sidebar-icon" aria-hidden="true">
                    👤
                  </span>
                  <span>Your work</span>
                </NavLink>
              </li>
              <li>
                <NavLink
                  to="/stickies"
                  className="kb-sidebar-nav-item"
                  aria-current={currentPath === '/stickies' ? 'page' : undefined}
                >
                  <span className="kb-sidebar-icon" aria-hidden="true">
                    🟨
                  </span>
                  <span>Stickies</span>
                </NavLink>
              </li>
            </ul>
          </nav>
        </div>

        {/* Projects Section */}
        <div className="kb-sidebar-section">
          <div className="kb-sidebar-heading">Projects</div>
          <nav aria-label="Projects navigation">
            <button
              type="button"
              className="kb-project-expand-row"
              aria-label={`Project: ${projectName}`}
              aria-expanded={projectExpanded}
              onClick={() => { setProjectExpanded(!projectExpanded); }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span aria-hidden="true">⚡</span>
                <span>{projectName}</span>
              </span>
              <span aria-hidden="true">{projectExpanded ? '▾' : '▸'}</span>
            </button>

            {projectExpanded && (
              <ul className="kb-project-subitems">
                <li>
                  <NavLink
                    to={`/projects/${projectKey}/issues`}
                    className="kb-sidebar-nav-item"
                    aria-current={
                      currentPath.startsWith(`/projects/${projectKey}/issues`)
                        ? 'page'
                        : undefined
                    }
                  >
                    <span className="kb-sidebar-icon" aria-hidden="true">
                      📋
                    </span>
                    <span>Work Items</span>
                  </NavLink>
                </li>
                <li>
                  <NavLink
                    to={`/projects/${projectKey}/cycles`}
                    className="kb-sidebar-nav-item"
                    aria-current={
                      currentPath.startsWith(`/projects/${projectKey}/cycles`)
                        ? 'page'
                        : undefined
                    }
                  >
                    <span className="kb-sidebar-icon" aria-hidden="true">
                      🔄
                    </span>
                    <span>Cycles</span>
                  </NavLink>
                </li>

                {/* Modules: ABSENT from DOM when modulesEnabled === false */}
                {modulesEnabled && (
                  <li>
                    <NavLink
                      to={`/projects/${projectKey}/modules`}
                      className="kb-sidebar-nav-item"
                      aria-current={
                        currentPath.startsWith(`/projects/${projectKey}/modules`)
                          ? 'page'
                          : undefined
                      }
                    >
                      <span className="kb-sidebar-icon" aria-hidden="true">
                        🧩
                      </span>
                      <span>Modules</span>
                    </NavLink>
                  </li>
                )}

                <li>
                  <NavLink
                    to={`/projects/${projectKey}/views`}
                    className="kb-sidebar-nav-item"
                    aria-current={
                      currentPath.startsWith(`/projects/${projectKey}/views`)
                        ? 'page'
                        : undefined
                    }
                  >
                    <span className="kb-sidebar-icon" aria-hidden="true">
                      🎛️
                    </span>
                    <span>Views</span>
                  </NavLink>
                </li>
                <li>
                  <NavLink
                    to={`/projects/${projectKey}/docs`}
                    className="kb-sidebar-nav-item"
                    aria-current={
                      currentPath.startsWith(`/projects/${projectKey}/docs`)
                        ? 'page'
                        : undefined
                    }
                  >
                    <span className="kb-sidebar-icon" aria-hidden="true">
                      📄
                    </span>
                    <span>Docs (Pages)</span>
                  </NavLink>
                </li>
              </ul>
            )}
          </nav>
        </div>

        {/* Footer Collapse Control */}
        <div className="kb-sidebar-footer">
          <button
            type="button"
            className="kb-sidebar-collapse-btn"
            aria-label="Collapse sidebar"
            onClick={toggleCollapsed}
          >
            <span aria-hidden="true">◀</span>
            <span>Collapse</span>
            <kbd style={{ fontSize: '10px', opacity: 0.7 }}>[</kbd>
          </button>
        </div>
      </aside>
    </>
  );
}
