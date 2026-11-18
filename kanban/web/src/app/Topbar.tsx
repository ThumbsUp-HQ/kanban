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
import { Breadcrumb } from './Breadcrumb';
import { HeaderPills, type AccessManifestData } from './HeaderPills';
import { LayoutSwitcher } from './LayoutSwitcher';
import { useTheme, type Theme } from '../theme/ThemeProvider';
import { type SystemStatus } from './useSystemStatus';
import { ensureSessionCsrfToken } from '../features/auth/useSessionGuard';
import './Topbar.css';

export interface TopbarUser {
  id?: string | null;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  is_server_admin?: boolean;
  is_workspace_admin?: boolean;
  workspace_role?: string | null;
  workspace_capabilities?: string[] | null;
}

export interface TopbarProps {
  isSidebarOpen?: boolean | undefined;
  onToggleSidebar?: (() => void) | undefined;
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
}

const THEME_OPTIONS: readonly { id: Theme; label: string; icon: string }[] = [
  { id: 'light', label: 'Light', icon: '☀️' },
  { id: 'dark', label: 'Dark', icon: '🌙' },
  { id: 'system', label: 'System', icon: '💻' },
] as const;

export function Topbar({
  isSidebarOpen = true,
  onToggleSidebar,
  onOpenPalette,
  workspaceName = 'kanban',
  projectKey = 'KAN',
  projectId,
  projectName = 'kanban',
  currentSection = 'Work Items',
  issueCount,
  showLayoutSwitcher: showLayoutOverride,
  accessManifest,
  systemStatus,
  user,
}: TopbarProps): JSX.Element {
  const loc = useLocation();
  const navigate = useNavigate();
  const locationPathname = loc.pathname;

  const isIssuesRoute =
    showLayoutOverride ??
    (locationPathname.includes('/issues') &&
      !/\/issues\/[A-Z0-9]+-[0-9]+/.exec(locationPathname));

  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  const avatarRef = useRef<HTMLDivElement>(null);
  const avatarButtonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const themeContext = useTheme();

  // Close avatar menu on outside click
  useEffect(() => {
    if (!avatarMenuOpen) return;
    const handleOutside = (e: MouseEvent): void => {
      if (avatarRef.current && !avatarRef.current.contains(e.target as Node)) {
        setAvatarMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
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

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!menuRef.current) return;
      const focusable = Array.from(
        menuRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
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
      setAvatarMenuOpen(false);
      void navigate('/login', { replace: true });
    }
  };

  const activeTheme = themeContext.theme;

  // Determine avatar initials or custom image
  const userInitial = user?.display_name ? user.display_name.charAt(0).toUpperCase() : 'A';
  const isServerAdmin = Boolean(user?.is_server_admin);
  const isWorkspaceAdmin = Boolean(user?.is_workspace_admin ?? user?.is_server_admin);

  return (
    <header className="kb-topbar">
      {/* Left: Hamburger & Breadcrumb */}
      <div className="kb-topbar-left">
        <button
          type="button"
          className="kb-topbar-hamburger"
          aria-label="Open navigation"
          aria-expanded={isSidebarOpen}
          onClick={onToggleSidebar}
        >
          ☰
        </button>
        <Breadcrumb
          workspaceName={workspaceName}
          projectKey={projectKey}
          projectName={projectName}
          currentSection={currentSection}
          issueCount={issueCount}
        />
      </div>

      {/* Center: Search Trigger Styled as Input */}
      <div className="kb-topbar-center">
        <button
          type="button"
          className="kb-search-trigger"
          aria-label="Search or run command"
          aria-keyshortcuts="Meta+K Control+K"
          onClick={onOpenPalette}
        >
          <div className="kb-search-trigger-content">
            <span aria-hidden="true">🔍</span>
            <span className="kb-search-trigger-text">Search / Cmd+K...</span>
          </div>
          <kbd className="kb-search-kbd">Cmd+K</kbd>
        </button>
      </div>

      {/* Right: Header Pills, Layout Switcher & Avatar Menu */}
      <div className="kb-topbar-right">
        <HeaderPills
          projectId={projectId ?? projectKey}
          projectName={projectName}
          accessManifest={accessManifest}
          systemStatus={systemStatus}
        />

        {isIssuesRoute && <LayoutSwitcher />}

        <div ref={avatarRef} className="kb-avatar-wrapper">
          <button
            ref={avatarButtonRef}
            type="button"
            className="kb-avatar-button"
            aria-label="User profile and settings"
            aria-haspopup="menu"
            aria-expanded={avatarMenuOpen}
            onClick={() => {
              setAvatarMenuOpen(!avatarMenuOpen);
            }}
          >
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.display_name ?? 'User avatar'}
                className="kb-avatar-img"
              />
            ) : (
              userInitial
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
              <div className="kb-theme-menu-title">Theme</div>
              <div
                className="kb-theme-radiogroup"
                role="radiogroup"
                aria-label="Theme"
              >
                {THEME_OPTIONS.map((opt) => {
                  const isChecked = activeTheme === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      role="radio"
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
                  className="kb-theme-radio kb-avatar-menu-link"
                  onClick={() => {
                    setAvatarMenuOpen(false);
                  }}
                >
                  <span>
                    <span aria-hidden="true" className="kb-avatar-menu-icon">
                      🔑
                    </span>
                    Personal MCP Keys
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
                      to="/workspaces/settings/mcp"
                      role="menuitem"
                      className="kb-theme-radio kb-avatar-menu-link"
                      onClick={() => {
                        setAvatarMenuOpen(false);
                      }}
                    >
                      <span>
                        <span aria-hidden="true" className="kb-avatar-menu-icon">
                          🔑
                        </span>
                        Workspace MCP Keys
                      </span>
                    </Link>
                  </>
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
                      to="/admin/mcp"
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
                        Admin MCP Keys
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
