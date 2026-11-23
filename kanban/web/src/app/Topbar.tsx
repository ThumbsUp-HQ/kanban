/**
 * Topbar Component (KB-P3-34, S6.3, KANBA-167, KANBA-186, KANBA-187, KANBA-188).
 * 52px calm header with breadcrumb, Cmd+K trigger, emoji pills, layout switcher,
 * and avatar menu with Theme selector, Settings/Admin navigation links, and Log out.
 * Enforces keyboard accessibility (Escape, ArrowDown/ArrowUp, focus return) and
 * gates admin navigation on `is_server_admin`.
 */

import React, {
  useEffect,
  useRef,
  useState,
  type JSX,
} from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';
import { Breadcrumb } from './Breadcrumb';
import { HeaderPills, type AccessManifestData } from './HeaderPills';
import { LayoutSwitcher } from './LayoutSwitcher';
import { NotificationsBell } from '../features/notifications/NotificationsBell';
import { useTheme, type Theme } from '../theme/ThemeProvider';
import { type SystemStatus } from './useSystemStatus';
import { ensureSessionCsrfToken } from '../features/auth/useSessionGuard';
import { PanelLeftOpen } from '../components/icons/KanbanIcons';
import './Topbar.css';

export interface TopbarUser {
  id?: string | null;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  handle?: string | null;
  is_server_admin?: boolean;
  is_workspace_admin?: boolean;
  workspace_role?: string | null;
  workspace_capabilities?: string[] | null;
}

export function resolveDisplayHandle(user?: TopbarUser | null): string {
  if (!user) return '';
  const rawHandle = user.handle?.trim();
  const isUuid = (val: string) =>
    /^[0-9a-f]{8}(-[0-9a-f]{4}){0,3}(-[0-9a-f]{4,12})?$/i.test(val.replace(/^@+/, ''));

  if (rawHandle && !isUuid(rawHandle)) {
    const clean = rawHandle.replace(/^@+/, '');
    return clean ? `@${clean}` : '@user';
  }

  // Derive from display_name or email, avoiding raw UUID leaks
  if (user.display_name && !isUuid(user.display_name)) {
    const slug = user.display_name
      .toLowerCase()
      .trim()
      .replace(/\s+/g, '.')
      .replace(/[^a-z0-9._-]/g, '');
    if (slug) return `@${slug}`;
  }

  if (user.email) {
    const parts = user.email.split('@');
    const emailPrefix = parts[0]?.trim();
    if (emailPrefix && !isUuid(emailPrefix)) return `@${emailPrefix}`;
  }

  if (user.id && !isUuid(user.id)) return `@${user.id}`;
  return '@user';
}

export interface TopbarProps {
  isSidebarOpen?: boolean | undefined;
  isSidebarCollapsed?: boolean | undefined;
  onToggleSidebar?: (() => void) | undefined;
  onToggleCollapse?: (() => void) | undefined;
  onOpenPalette?: (() => void) | undefined;
  workspaceName?: string | undefined;
  projectKey?: string | undefined;
  projectId?: string | undefined;
  projectName?: string | undefined;
  currentSection?: string | undefined;
  issueCount?: number | null | undefined;
  showLayoutSwitcher?: boolean | undefined;
  accessManifest?: AccessManifestData | null | undefined;
  systemStatus?: SystemStatus | null | undefined;
  user?: TopbarUser | null | undefined;
  hamburgerButtonRef?: React.RefObject<HTMLButtonElement | null> | undefined;
}

const THEME_OPTIONS: readonly { id: Theme; label: string; icon: string }[] = [
  { id: 'light', label: 'Light', icon: '☀️' },
  { id: 'dark', label: 'Dark', icon: '🌙' },
  { id: 'system', label: 'System', icon: '💻' },
] as const;

export function Topbar({
  isSidebarOpen = true,
  isSidebarCollapsed = false,
  onToggleSidebar,
  onToggleCollapse,
  onOpenPalette,
  workspaceName = 'kanban',
  projectKey,
  projectId,
  projectName = 'kanban',
  currentSection = 'Work Items',
  issueCount,
  showLayoutSwitcher: showLayoutOverride,
  accessManifest,
  systemStatus,
  user,
  hamburgerButtonRef,
}: TopbarProps): JSX.Element {
  const loc = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const locationPathname = loc.pathname;

  const isIssuesRoute =
    showLayoutOverride ??
    (locationPathname.includes('/issues') &&
      !/\/issues\/[A-Z0-9]+-[0-9]+/.exec(locationPathname));

  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  const [failedAvatarUrl, setFailedAvatarUrl] = useState<string | null>(null);
  const isAvatarBroken = Boolean(user?.avatar_url && failedAvatarUrl === user.avatar_url);
  const avatarRef = useRef<HTMLDivElement>(null);
  const avatarButtonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const themeContext = useTheme();

  useEffect(() => {
    const handleStatusChanged = (): void => {
      void queryClient.invalidateQueries({ queryKey: qk.systemStatus() });
      void queryClient.invalidateQueries({ queryKey: ['system', 'status'] });
    };
    window.addEventListener('kb:system-status-changed', handleStatusChanged);
    return () => {
      window.removeEventListener('kb:system-status-changed', handleStatusChanged);
    };
  }, [queryClient]);

  // Close avatar menu on outside click or Escape
  useEffect(() => {
    if (!avatarMenuOpen) return;
    const handleOutside = (e: MouseEvent): void => {
      if (avatarRef.current && !avatarRef.current.contains(e.target as Node)) {
        setAvatarMenuOpen(false);
      }
    };
    const handleGlobalKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setAvatarMenuOpen(false);
        avatarButtonRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', handleOutside);
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
      window.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [avatarMenuOpen]);

  // Handle keyboard navigation within the menu
  const handleMenuKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      setAvatarMenuOpen(false);
      avatarButtonRef.current?.focus();
      return;
    }

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      if (!menuRef.current) return;
      const focusable = Array.from(
        menuRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      if (e.key === 'Home') {
        focusable[0]?.focus();
        return;
      }
      if (e.key === 'End') {
        focusable[focusable.length - 1]?.focus();
        return;
      }
      const currentIndex = focusable.indexOf(document.activeElement as HTMLElement);
      let nextIndex = 0;
      if (e.key === 'ArrowDown') {
        nextIndex = currentIndex >= 0 && currentIndex < focusable.length - 1 ? currentIndex + 1 : 0;
      } else {
        nextIndex = currentIndex > 0 ? currentIndex - 1 : focusable.length - 1;
      }
      focusable[nextIndex]?.focus();
    }
  };

  const handleLogout = async (): Promise<void> => {
    try {
      const csrfToken = await ensureSessionCsrfToken();
      const headers: Record<string, string> = {
        Accept: 'application/json',
      };
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
      });
    } catch {
      // Proceed to login redirect even if network request fails
    } finally {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('kb:auth-logout'));
      }
      void queryClient.invalidateQueries({ queryKey: ['auth', 'session'] });
      setAvatarMenuOpen(false);
      void navigate('/login', { replace: true });
    }
  };

  const activeTheme = themeContext.theme;

  // Determine avatar initials or custom image
  const trimmedDisplayName = user?.display_name?.trim();
  const trimmedEmail = user?.email?.trim();
  const validHandle =
    user?.handle && !/^[0-9a-f]{8}/i.test(user.handle.replace(/^@+/, ''))
      ? user.handle.replace(/^@+/, '')
      : null;
  const userInitial = (
    (trimmedDisplayName && trimmedDisplayName.length > 0 ? trimmedDisplayName : null) ??
    validHandle ??
    (trimmedEmail && trimmedEmail.length > 0 ? trimmedEmail : null) ??
    'A'
  )
    .charAt(0)
    .toUpperCase();
  const isServerAdmin = Boolean(user?.is_server_admin);
  const isWorkspaceAdmin = Boolean(user?.is_workspace_admin ?? user?.is_server_admin);

  return (
    <header className="kb-topbar topbar">
      {/* Left: Hamburger (<=1279px) & Expand Button (desktop >=1280px when collapsed) & Breadcrumb */}
      <div className="kb-topbar-left">
        <button
          ref={hamburgerButtonRef}
          type="button"
          className="kb-topbar-hamburger"
          aria-label="Open navigation"
          aria-expanded={isSidebarOpen}
          onClick={onToggleSidebar}
        >
          ☰
        </button>
        {isSidebarCollapsed && (
          <button
            type="button"
            className="kb-topbar-expand-btn"
            aria-label="Expand navigation sidebar"
            title="Expand sidebar ([)"
            onClick={onToggleCollapse}
          >
            <PanelLeftOpen size={16} />
          </button>
        )}
        <Breadcrumb
          workspaceName={workspaceName}
          projectKey={projectKey}
          projectName={projectName}
          currentSection={currentSection}
          issueCount={issueCount}
        />
      </div>

      {/* Center: Search Trigger Styled as Input */}
      <div className="kb-topbar-center topbar__search">
        <button
          type="button"
          className="kb-search-trigger"
          aria-label="Search... (Cmd+K)"
          aria-keyshortcuts="Meta+K Control+K"
          onClick={onOpenPalette}
        >
          <div className="kb-search-trigger-content">
            <span aria-hidden="true">🔍</span>
            <span className="kb-search-trigger-text">Search...</span>
          </div>
          <kbd className="kb-search-kbd">Cmd+K</kbd>
        </button>
      </div>

      {/* Right: Header Pills, Layout Switcher & Avatar Menu */}
      <div className="kb-topbar-right topbar__right">
        <HeaderPills
          projectId={projectId ?? projectKey}
          projectName={projectName}
          accessManifest={accessManifest}
          systemStatus={systemStatus}
        />

        {isIssuesRoute && <LayoutSwitcher />}

        <Link
          to="/docs"
          className="kb-topbar-docs-btn"
          data-testid="topbar-docs-link"
          title="Documentation Center"
          aria-label="Documentation Center"
        >
          <span aria-hidden="true">&#128214;</span>
        </Link>

        <NotificationsBell />

        <div ref={avatarRef} className="kb-avatar-wrapper">
          <button
            ref={avatarButtonRef}
            type="button"
            className="kb-avatar-button"
            data-testid="topbar-avatar-button"
            aria-label="User profile and settings"
            aria-haspopup="menu"
            aria-expanded={avatarMenuOpen}
            onClick={() => {
              setAvatarMenuOpen(!avatarMenuOpen);
            }}
          >
            {user?.avatar_url && !isAvatarBroken ? (
              <img
                src={user.avatar_url}
                alt={user.display_name ?? 'User avatar'}
                className="kb-avatar-img"
                data-testid="topbar-avatar-img"
                draggable={false}
                onError={() => {
                  setFailedAvatarUrl(user.avatar_url ?? null);
                }}
              />
            ) : (
              <span data-testid="topbar-avatar-initial">{userInitial}</span>
            )}
          </button>

          {avatarMenuOpen && (
            <div
              ref={menuRef}
              className="kb-avatar-menu"
              role="menu"
              aria-label="User settings"
              onKeyDown={handleMenuKeyDown}
            >
              {user && (
                <>
                  <div className="kb-avatar-user-card" data-testid="topbar-user-profile">
                    <div className="kb-avatar-user-card-avatar">
                      {user.avatar_url && !isAvatarBroken ? (
                        <img
                          src={user.avatar_url}
                          alt={user.display_name ?? 'User avatar'}
                          className="kb-avatar-img"
                          draggable={false}
                          onError={() => {
                            setFailedAvatarUrl(user.avatar_url ?? null);
                          }}
                        />
                      ) : (
                        <span className="kb-avatar-fallback">{userInitial}</span>
                      )}
                    </div>
                    <div className="kb-avatar-user-card-info">
                      <div className="kb-avatar-user-card-name" data-testid="topbar-user-name">
                        {user.display_name ?? user.email ?? 'User'}
                      </div>
                      <div className="kb-avatar-user-card-handle" data-testid="topbar-user-handle">
                        {resolveDisplayHandle(user)}
                      </div>
                    </div>
                  </div>
                  <div className="kb-avatar-menu-divider" />
                </>
              )}
              <div className="kb-theme-menu-title">Theme</div>
              <div
                className="kb-theme-radiogroup"
                role="group"
                aria-label="Theme preference"
              >
                {THEME_OPTIONS.map((opt) => {
                  const isChecked = activeTheme === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={isChecked}
                      className="kb-theme-radio"
                      onClick={() => {
                        themeContext.setTheme(opt.id);
                        setAvatarMenuOpen(false);
                        avatarButtonRef.current?.focus();
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          {opt.icon}
                        </span>
                        {opt.label}
                      </span>
                      {isChecked && <span aria-hidden="true">✓</span>}
                    </button>
                  );
                })}
              </div>

              <div className="kb-avatar-menu-divider" />

              <div className="kb-theme-menu-title">Settings & Admin</div>
              <div className="kb-avatar-menu-list">
                {/* Personal Settings Studio (KANBA-187) */}
                <Link
                  to="/settings/profile"
                  role="menuitem"
                  data-testid="topbar-personal-settings-link"
                  className="kb-theme-radio kb-avatar-menu-link"
                  onClick={() => {
                    setAvatarMenuOpen(false);
                  }}
                >
                  <span>
                    <span aria-hidden="true" className="kb-avatar-menu-icon">
                      👤
                    </span>
                    Personal Settings
                  </span>
                </Link>

                <Link
                  to="/settings/mcp"
                  role="menuitem"
                  data-testid="topbar-mcp-studio-link"
                  className="kb-theme-radio kb-avatar-menu-link"
                  onClick={() => {
                    setAvatarMenuOpen(false);
                  }}
                >
                  <span>
                    <span aria-hidden="true" className="kb-avatar-menu-icon">
                      🔑
                    </span>
                    MCP Keys & OAuth Apps
                  </span>
                </Link>

                {isWorkspaceAdmin && (
                  <>
                    <Link
                      to="/workspaces/settings"
                      role="menuitem"
                      data-testid="topbar-workspace-settings-link"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🏢
                        </span>
                        Workspace Settings
                      </span>
                    </Link>

                    <Link
                      to="/workspaces/settings/ai"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🧠
                        </span>
                        Workspace AI Studio
                      </span>
                    </Link>
                  </>
                )}

                {(isWorkspaceAdmin || isServerAdmin) && (
                  <Link
                    to="/admin/link-auditor"
                    role="menuitem"
                    data-testid="topbar-link-auditor-link"
                    className="kb-theme-radio kb-avatar-menu-link"
                    onClick={() => {
                      setAvatarMenuOpen(false);
                    }}
                  >
                    <span>
                      <span aria-hidden="true" className="kb-avatar-menu-icon">
                        🩺
                      </span>
                      Diagnostics & Link Inspector
                    </span>
                  </Link>
                )}

                {isServerAdmin && (
                  <>
                    <Link
                      to="/admin/auth"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🛡️
                        </span>
                        Admin Auth Studio
                      </span>
                    </Link>

                    <Link
                      to="/admin/ai"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🧠
                        </span>
                        AI Providers & Token Caps
                      </span>
                    </Link>

                    <Link
                      to="/admin/agents"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🤖
                        </span>
                        Autonomous Agents
                      </span>
                    </Link>

                    <Link
                      to="/admin/agent-runners"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🚀
                        </span>
                        Remote mTLS Runners
                      </span>
                    </Link>

                    {/* Preserving System Storage, Backups & Deployment from KANBA-188 */}
                    <Link
                      to="/admin/standalone"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          💾
                        </span>
                        System Storage, Backups & Deployment
                      </span>
                    </Link>
                  </>
                )}
              </div>

              <Link
                to="/docs"
                role="menuitem"
                data-testid="topbar-avatar-docs-link"
                className="kb-theme-radio kb-avatar-menu-link"
                onClick={() => {
                  setAvatarMenuOpen(false);
                }}
              >
                <span>
                  <span aria-hidden="true" className="kb-avatar-menu-icon">
                    📖
                  </span>
                  Documentation
                </span>
              </Link>

              <Link
                to="/about"
                role="menuitem"
                data-testid="topbar-about-link"
                className="kb-theme-radio kb-avatar-menu-link"
                onClick={() => {
                  setAvatarMenuOpen(false);
                }}
              >
                <span>
                  <span aria-hidden="true" className="kb-avatar-menu-icon">
                    ℹ️
                  </span>
                  About 👍kanban
                </span>
              </Link>

              <div className="kb-avatar-menu-divider" />

              <button
                type="button"
                role="menuitem"
                data-testid="logout-button"
                className="kb-theme-radio kb-avatar-logout"
                onClick={() => {
                  void handleLogout();
                }}
              >
                <span>
                  <span aria-hidden="true" className="kb-avatar-menu-icon">
                    🚪
                  </span>
                  Log out
                </span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
