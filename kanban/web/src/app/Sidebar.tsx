/**
 * Sidebar Navigation Rail (KB-P3-34, S6.3, KANBA-166, KANBA-167).
 * 256px collapsible navigation rail with Plane parity, [👍] 👍kanban branding,
 * dynamic project list, project creation modal, and accessible keyboard focus trapping.
 */

import React, {
  useCallback,
  useContext,
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
import { CreateWorkspaceModal, type CreatedWorkspace } from '../features/workspaces/CreateWorkspaceModal';
import { ensureSessionCsrfToken } from '../features/auth/useSessionGuard';
import { setCsrfToken } from '../api/client';
import { QueryClientContext } from '@tanstack/react-query';
import {
  ListTodo,
  Kanban,
  Table2,
  CalendarDays,
  GanttChart,
  PanelLeftClose,
} from '../components/icons/KanbanIcons';
import './Sidebar.css';

export interface WorkspaceNavData {
  id: string;
  name: string;
  slug: string;
  is_current?: boolean;
  role?: string | null;
}

export interface ProjectNavData {
  key: string;
  name: string;
  modules_enabled?: boolean | undefined;
  is_project_admin?: boolean | undefined;
  capabilities?: string[] | undefined;
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
  user?: {
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    workspace_role?: string | null;
    workspace_capabilities?: string[] | null;
  } | null | undefined;
}

export const SIDEBAR_STORAGE_KEY = 'kb.sidebar';

export function sanitizeSidebarState(value: string | null): 'open' | 'collapsed' {
  if (value === 'open' || value === 'collapsed') {
    return value;
  }
  return 'open';
}

async function fetchWorkspaces(): Promise<WorkspaceNavData[]> {
  try {
    const res = await fetch('/api/v1/workspaces', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    if (res.ok) {
      const data = (await res.json()) as WorkspaceNavData[];
      if (Array.isArray(data)) {
        return data;
      }
    }
  } catch {
    // Offline / unit test fallback
  }
  return [];
}

async function fetchProjects(): Promise<ProjectNavData[]> {
  try {
    const res = await fetch('/api/v1/projects', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    if (!res.ok) {
      return [];
    }
    const data = (await res.json()) as
      | {
          items?: {
            identifier?: string;
            key?: string;
            name?: string;
            modules_enabled?: boolean;
            is_project_admin?: boolean;
            capabilities?: string[];
          }[];
        }
      | {
          identifier?: string;
          key?: string;
          name?: string;
          modules_enabled?: boolean;
          is_project_admin?: boolean;
          capabilities?: string[];
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
          is_project_admin: item.is_project_admin,
          capabilities: item.capabilities,
        });
      }
    }
    return parsed;
  } catch {
    // Offline or unmocked unit test environment
    return [];
  }
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
  user,
}: SidebarProps): JSX.Element {
  let locationPathname = '';
  let locationSearch = '';
  try {
    const loc = useLocation();
    locationPathname = loc.pathname;
    locationSearch = loc.search;
  } catch {
    // Outside Router
  }

  const currentLayout = useMemo(() => {
    try {
      const search = locationSearch || (typeof window !== 'undefined' ? window.location.search : '');
      const params = new URLSearchParams(search);
      return params.get('layout') ?? 'list';
    } catch {
      return 'list';
    }
  }, [locationSearch]);

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

  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const [fetchedProjects, setFetchedProjects] = useState<ProjectNavData[]>([]);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<WorkspaceNavData[]>([]);
  const [workspaceDropdownOpen, setWorkspaceDropdownOpen] = useState(false);
  const [createWorkspaceOpen, setCreateWorkspaceOpen] = useState(false);

  const queryClient = useContext(QueryClientContext);
  const sidebarRef = useRef<HTMLElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);
  const workspaceSwitcherRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    void fetchWorkspaces().then((data) => {
      if (active && data.length > 0) {
        setWorkspaces(data);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!workspaceDropdownOpen) return;
    const handleOutsideClick = (e: MouseEvent): void => {
      if (
        workspaceSwitcherRef.current &&
        !workspaceSwitcherRef.current.contains(e.target as Node)
      ) {
        setWorkspaceDropdownOpen(false);
      }
    };
    const handleKeyDown = (e: globalThis.KeyboardEvent): void => {
      if (e.key === 'Escape') {
        setWorkspaceDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [workspaceDropdownOpen]);

  const handleSwitchWorkspace = async (targetId: string): Promise<void> => {
    setWorkspaceDropdownOpen(false);
    try {
      const csrfToken = await ensureSessionCsrfToken();
      const headers: Record<string, string> = {
        Accept: 'application/json',
      };
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }
      const res = await fetch(`/api/v1/workspaces/${targetId}/switch`, {
        method: 'POST',
        headers,
        credentials: 'same-origin',
      });
      if (res.ok) {
        const data = (await res.json().catch(() => ({}))) as { csrf_token?: string };
        if (data.csrf_token) {
          setCsrfToken(data.csrf_token);
        }
        queryClient?.clear();

        // Update local workspace current flag immediately
        setWorkspaces((prev) =>
          prev.map((w) => ({
            ...w,
            is_current: w.id === targetId,
          })),
        );

        // Re-fetch workspaces and projects in new workspace
        const updatedWorkspaces = await fetchWorkspaces();
        if (updatedWorkspaces.length > 0) {
          setWorkspaces(updatedWorkspaces);
        }
        const updatedProjects = await fetchProjects();
        setFetchedProjects(updatedProjects);

        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('kb:workspace-switched', { detail: { workspaceId: targetId } }),
          );
        }

        const firstProj = updatedProjects[0];
        const targetRoute =
          firstProj !== undefined
            ? `/projects/${firstProj.key}/issues`
            : '/';
        if (navigateFn) {
          navigateFn(targetRoute);
        } else if (typeof window !== 'undefined') {
          window.location.assign(targetRoute);
        }
      }
    } catch {
      // Ignore
    }
  };

  const handleWorkspaceCreated = (created: CreatedWorkspace): void => {
    setWorkspaces((prev) => [
      ...prev,
      {
        id: created.id,
        name: created.name,
        slug: created.slug,
        is_current: false,
      },
    ]);
    void handleSwitchWorkspace(created.id);
  };

  const currentWorkspace = useMemo(() => {
    return (
      workspaces.find((w) => w.is_current) ?? {
        id: '',
        name: '👍kanban',
        slug: 'kanban',
      }
    );
  }, [workspaces]);

  useEffect(() => {
    let active = true;
    const refresh = (): void => {
      void fetchProjects().then((items) => {
        if (active && items.length > 0) {
          setFetchedProjects(items);
        }
      });
    };
    refresh();

    const handleProjectCreated = (e: Event): void => {
      const customEvent = e as CustomEvent<{ identifier?: string; key?: string; name?: string; modules_enabled?: boolean } | null | undefined>;
      const detail = customEvent.detail;
      if (detail && typeof detail.name === 'string') {
        const key = detail.identifier ?? detail.key;
        const projName = detail.name;
        if (typeof key === 'string' && key.length > 0) {
          setFetchedProjects((prev) => {
            if (prev.some((p) => p.key === key)) return prev;
            return [
              ...prev,
              {
                key,
                name: projName,
                modules_enabled: detail.modules_enabled ?? true,
              },
            ];
          });
        }
      }
      refresh();
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
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('kb:sidebar-changed', {
              detail: { collapsed: next },
            }),
          );
        }
      } catch {
        // Ignore storage errors
      }
      return next;
    });
    onToggleCollapse?.();
  }, [onToggleCollapse]);

  // Listen for external toggle events (e.g. from IssueSurface header Hide Nav / Show Nav)
  useEffect(() => {
    const handleExternalToggle = (): void => {
      toggleCollapsed();
    };
    window.addEventListener('kb:toggle-sidebar', handleExternalToggle);
    return () => {
      window.removeEventListener('kb:toggle-sidebar', handleExternalToggle);
    };
  }, [toggleCollapsed]);

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
        {/* Workspace Brand & Switcher & New Item Button */}
        <div className="kb-sidebar-header">
          <div className="kb-workspace-switcher-wrapper" ref={workspaceSwitcherRef}>
            <button
              ref={firstItemRef}
              type="button"
              className="kb-workspace-switcher"
              aria-label={`Workspace switcher: [👍] ${currentWorkspace.name}`}
              aria-expanded={workspaceDropdownOpen}
              aria-haspopup="true"
              onClick={() => {
                setWorkspaceDropdownOpen((prev) => !prev);
              }}
            >
              <span className="kb-workspace-brand">
                <span aria-hidden="true">[👍]</span>
                <span>{currentWorkspace.name}</span>
              </span>
              <span aria-hidden="true">▾</span>
            </button>

            {workspaceDropdownOpen && (
              <div className="kb-workspace-dropdown" role="menu">
                {workspaces.map((ws) => (
                  <button
                    key={ws.id}
                    type="button"
                    role="menuitem"
                    className={`kb-workspace-dropdown-item ${
                      ws.is_current ? 'kb-workspace-dropdown-item-active' : ''
                    }`}
                    onClick={() => void handleSwitchWorkspace(ws.id)}
                  >
                    <span className="kb-workspace-dropdown-name">
                      <span aria-hidden="true">[👍]</span>
                      <span>{ws.name}</span>
                    </span>
                    {ws.is_current && <span className="kb-workspace-dropdown-check">✓</span>}
                  </button>
                ))}
                {workspaces.length > 0 && <div className="kb-workspace-dropdown-divider" />}
                {Boolean(user?.is_workspace_admin ?? user?.is_server_admin) && (
                  <NavLink
                    to="/workspaces/settings"
                    role="menuitem"
                    className="kb-workspace-dropdown-item"
                    onClick={() => {
                      setWorkspaceDropdownOpen(false);
                    }}
                  >
                    <span className="kb-workspace-dropdown-name">
                      <span className="kb-sidebar-icon" aria-hidden="true">
                        ⚙️
                      </span>
                      <span>Workspace Settings</span>
                    </span>
                  </NavLink>
                )}
                <button
                  type="button"
                  role="menuitem"
                  className="kb-workspace-dropdown-create-btn"
                  onClick={() => {
                    setWorkspaceDropdownOpen(false);
                    setCreateWorkspaceOpen(true);
                  }}
                >
                  <span aria-hidden="true">+</span>
                  <span>Create New Workspace</span>
                </button>
              </div>
            )}
          </div>

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
              const isProjExpanded = expandedProjects[proj.key] ?? true;
              return (
                <div key={proj.key}>
                  <button
                    type="button"
                    className="kb-project-expand-row"
                    aria-label={`Project: ${proj.name}`}
                    aria-expanded={isProjExpanded}
                    onClick={() => {
                      setExpandedProjects((prev) => ({
                        ...prev,
                        [proj.key]: !isProjExpanded,
                      }));
                    }}
                  >
                    <span className="kb-project-expand-label">
                      <span aria-hidden="true">⚡</span>
                      <span>{proj.name}</span>
                    </span>
                    <span aria-hidden="true">{isProjExpanded ? '▾' : '▸'}</span>
                  </button>

                  {isProjExpanded && (
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

                        {/* Project Layout Views (KANBA-174) */}
                        <ul className="kb-project-views-list" aria-label="Project views">
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/issues?layout=list`}
                              className={`kb-sidebar-nav-item kb-sidebar-subnav-item ${
                                currentPath.startsWith(`/projects/${proj.key}/issues`) &&
                                currentLayout === 'list'
                                  ? 'kb-subnav-active'
                                  : ''
                              }`}
                              aria-label="List view"
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                <ListTodo size={14} />
                              </span>
                              <span>📋 List</span>
                            </NavLink>
                          </li>
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/issues?layout=board`}
                              className={`kb-sidebar-nav-item kb-sidebar-subnav-item ${
                                currentPath.startsWith(`/projects/${proj.key}/issues`) &&
                                currentLayout === 'board'
                                  ? 'kb-subnav-active'
                                  : ''
                              }`}
                              aria-label="Board view"
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                <Kanban size={14} />
                              </span>
                              <span>📊 Board</span>
                            </NavLink>
                          </li>
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/issues?layout=table`}
                              className={`kb-sidebar-nav-item kb-sidebar-subnav-item ${
                                currentPath.startsWith(`/projects/${proj.key}/issues`) &&
                                currentLayout === 'table'
                                  ? 'kb-subnav-active'
                                  : ''
                              }`}
                              aria-label="Table view"
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                <Table2 size={14} />
                              </span>
                              <span>📑 Table</span>
                            </NavLink>
                          </li>
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/issues?layout=calendar`}
                              className={`kb-sidebar-nav-item kb-sidebar-subnav-item ${
                                currentPath.startsWith(`/projects/${proj.key}/issues`) &&
                                currentLayout === 'calendar'
                                  ? 'kb-subnav-active'
                                  : ''
                              }`}
                              aria-label="Calendar view"
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                <CalendarDays size={14} />
                              </span>
                              <span>📅 Calendar</span>
                            </NavLink>
                          </li>
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/issues?layout=timeline`}
                              className={`kb-sidebar-nav-item kb-sidebar-subnav-item ${
                                currentPath.startsWith(`/projects/${proj.key}/issues`) &&
                                currentLayout === 'timeline'
                                  ? 'kb-subnav-active'
                                  : ''
                              }`}
                              aria-label="Timeline view"
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                <GanttChart size={14} />
                              </span>
                              <span>📈 Timeline</span>
                            </NavLink>
                          </li>
                        </ul>
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
                          <span>Docs</span>
                        </NavLink>
                      </li>
                      {(proj.is_project_admin ??
                        proj.capabilities?.includes('ADMIN') ??
                        proj.capabilities?.includes('PROJECT_ADMIN') ??
                        user?.is_server_admin ??
                        user?.is_workspace_admin ??
                        (proj.capabilities ?? proj.is_project_admin) === undefined) && (
                        <>
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/settings/workflows`}
                              className="kb-sidebar-nav-item"
                              aria-current={
                                currentPath.startsWith(
                                  `/projects/${proj.key}/settings/workflows`,
                                )
                                  ? 'page'
                                  : undefined
                              }
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                🔀
                              </span>
                              <span>Workflows</span>
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
                          <li>
                            <NavLink
                              to={`/projects/${proj.key}/settings`}
                              className="kb-sidebar-nav-item"
                              data-testid={`sidebar-project-settings-${proj.key}`}
                              aria-current={
                                currentPath === `/projects/${proj.key}/settings`
                                  ? 'page'
                                  : undefined
                              }
                            >
                              <span className="kb-sidebar-icon" aria-hidden="true">
                                ⚙️
                              </span>
                              <span>Project Settings</span>
                            </NavLink>
                          </li>
                        </>
                      )}
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
            aria-label="Collapse sidebar (Hide Nav)"
            onClick={toggleCollapsed}
          >
            <span aria-hidden="true">
              <PanelLeftClose size={14} />
            </span>
            <span>Hide Nav</span>
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

      <CreateWorkspaceModal
        isOpen={createWorkspaceOpen}
        onClose={() => {
          setCreateWorkspaceOpen(false);
        }}
        onCreated={handleWorkspaceCreated}
      />
    </>
  );
}
