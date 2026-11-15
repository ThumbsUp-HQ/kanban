/**
 * Sidebar Navigation Rail (KB-P3-34, S6.3, KANBA-166, KANBA-167).
 * 256px collapsible navigation rail with Plane parity, [👍] 👍kanban branding,
 * dynamic project list, project creation modal, and accessible keyboard focus trapping.
 */

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router';
import { registerShortcut } from './shortcuts';
import { CreateProjectModal } from '../features/projects/CreateProjectModal';
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

  let navigateFn: ((to: string) => void) | null = null;
  try {
    const nav = useNavigate();
    navigateFn = (to: string) => {
      void nav(to);
    };
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
  const [fetchedProjects, setFetchedProjects] = useState<ProjectNavData[]>([]);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);

  const sidebarRef = useRef<HTMLElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;

    async function loadProjects(): Promise<void> {
      try {
        const res = await fetch('/api/v1/projects', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        });
        if (!res.ok || !active) {
          return;
        }
        const data = (await res.json()) as
          | {
              items?: {
                identifier?: string;
                key?: string;
                name?: string;
                modules_enabled?: boolean;
              }[];
            }
          | {
              identifier?: string;
              key?: string;
              name?: string;
              modules_enabled?: boolean;
            }[];
        const rawItems = Array.isArray(data) ? data : (data.items ?? []);
        const parsed: ProjectNavData[] = [];
        for (const item of rawItems) {
          const key = item.identifier ?? item.key;
          if (typeof key === 'string' && key.length > 0 && typeof item.name === 'string') {
            parsed.push({
              key,
              name: item.name,
              modules_enabled: item.modules_enabled ?? true,
            });
          }
        }
        if (parsed.length > 0) {
          setFetchedProjects(parsed);
        }
      } catch {
        // Offline or unmocked unit test environment
      }
    }

    void loadProjects();

    const handleProjectCreated = (): void => {
      void loadProjects();
    };
    const handleOpenCreateProject = (): void => {
      setCreateProjectOpen(true);
    };

    window.addEventListener('kb:project-created', handleProjectCreated);
    window.addEventListener('kb:open-create-project', handleOpenCreateProject);
    return () => {
      active = false;
      window.removeEventListener('kb:project-created', handleProjectCreated);
      window.removeEventListener('kb:open-create-project', handleOpenCreateProject);
    };
  }, []);

  const projectList = useMemo<ProjectNavData[]>(() => {
    const primary: ProjectNavData = {
      key: projectKey,
      name: projectName,
      modules_enabled: modulesEnabled,
    };
    if (fetchedProjects.length === 0) {
      return [primary];
    }
    const hasPrimaryInFetched = fetchedProjects.some((p) => p.key === projectKey);
    if (hasPrimaryInFetched) {
      return fetchedProjects.map((p) =>
        p.key === projectKey && projectName !== 'kanban'
          ? { key: p.key, name: projectName, modules_enabled: modulesEnabled }
          : p,
      );
    }
    if (projectName !== 'kanban' || currentPath.startsWith(`/projects/${projectKey}`)) {
      return [primary, ...fetchedProjects];
    }
    return fetchedProjects;
  }, [fetchedProjects, projectKey, projectName, modulesEnabled, currentPath]);

  const activeProjectKey = projectList[0]?.key ?? projectKey;

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

    return () => {
      clearTimeout(timer);
    };
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
    if (navigateFn && !currentPath.startsWith(`/projects/${activeProjectKey}/issues`)) {
      navigateFn(`/projects/${activeProjectKey}/issues?create=1`);
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
        role={
          isOpen && typeof window !== 'undefined' && window.innerWidth <= 1279
            ? 'dialog'
            : undefined
        }
        aria-modal={
          isOpen && typeof window !== 'undefined' && window.innerWidth <= 1279
            ? 'true'
            : undefined
        }
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
          <div className="kb-sidebar-heading-row">
            <div className="kb-sidebar-heading">
              Projects
            </div>
            <button
              type="button"
              className="kb-sidebar-add-project-btn"
              aria-label="Create project"
              title="Create project"
              onClick={() => {
                setCreateProjectOpen(true);
              }}
            >
              + Project
            </button>
          </div>
          <nav aria-label="Projects navigation">
            {projectList.map((proj) => {
              const projModulesEnabled = proj.modules_enabled ?? modulesEnabled;
              return (
                <div key={proj.key}>
                  <button
                    type="button"
                    className="kb-project-expand-row"
                    aria-label={`Project: ${proj.name}`}
                    aria-expanded={projectExpanded}
                    onClick={() => {
                      setProjectExpanded(!projectExpanded);
                    }}
                  >
                    <span className="kb-project-expand-label">
                      <span aria-hidden="true">⚡</span>
                      <span>{proj.name}</span>
                    </span>
                    <span aria-hidden="true">{projectExpanded ? '▾' : '▸'}</span>
                  </button>

                  {projectExpanded && (
                    <ul className="kb-project-subitems">
                      <li>
                        <NavLink
                          to={`/projects/${proj.key}/issues`}
                          className="kb-sidebar-nav-item"
                          aria-current={
                            currentPath.startsWith(`/projects/${proj.key}/issues`)
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
                          to={`/projects/${proj.key}/cycles`}
                          className="kb-sidebar-nav-item"
                          aria-current={
                            currentPath.startsWith(`/projects/${proj.key}/cycles`)
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

                      {/* Modules: ABSENT from DOM when projModulesEnabled === false */}
                      {projModulesEnabled && (
                        <li>
                          <NavLink
                            to={`/projects/${proj.key}/modules`}
                            className="kb-sidebar-nav-item"
                            aria-current={
                              currentPath.startsWith(`/projects/${proj.key}/modules`)
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
                          to={`/projects/${proj.key}/views`}
                          className="kb-sidebar-nav-item"
                          aria-current={
                            currentPath.startsWith(`/projects/${proj.key}/views`)
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
                          to={`/projects/${proj.key}/docs`}
                          className="kb-sidebar-nav-item"
                          aria-current={
                            currentPath.startsWith(`/projects/${proj.key}/docs`)
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
                      <li>
                        <NavLink
                          to={`/projects/${proj.key}/settings/custom-fields`}
                          className="kb-sidebar-nav-item"
                          aria-current={
                            currentPath.startsWith(
                              `/projects/${proj.key}/settings/custom-fields`,
                            )
                              ? 'page'
                              : undefined
                          }
                        >
                          <span className="kb-sidebar-icon" aria-hidden="true">
                            ⚙️
                          </span>
                          <span>Custom Fields</span>
                        </NavLink>
                      </li>
                    </ul>
                  )}
                </div>
              );
            })}
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
            <kbd className="kb-sidebar-collapse-kbd">[</kbd>
          </button>
        </div>
      </aside>

      <CreateProjectModal
        isOpen={createProjectOpen}
        onClose={() => {
          setCreateProjectOpen(false);
        }}
        onCreated={(created) => {
          setFetchedProjects((prev) => {
            const exists = prev.some((p) => p.key === created.identifier);
            if (exists) return prev;
            return [
              ...prev,
              {
                key: created.identifier,
                name: created.name,
                modules_enabled: created.modules_enabled ?? true,
              },
            ];
          });
        }}
      />
    </>
  );
}
