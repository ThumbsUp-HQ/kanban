/**
 * Topbar Component (KB-P3-34, S6.3, KANBA-167).
 * 52px calm header with breadcrumb, Cmd+K trigger, emoji pills, layout switcher,
 * and avatar menu with Theme selector, Settings/Admin navigation links, and Log out.
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

export interface TopbarProps {
  isSidebarOpen?: boolean | undefined;
  onToggleSidebar?: (() => void) | undefined;
  onOpenPalette?: (() => void) | undefined;
  projectKey?: string | undefined;
  projectName?: string | undefined;
  currentSection?: string | undefined;
  issueCount?: number | null | undefined;
  showLayoutSwitcher?: boolean | undefined;
  accessManifest?: AccessManifestData | null | undefined;
  systemStatus?: SystemStatus | null | undefined;
}

const THEME_OPTIONS: readonly { id: Theme; label: string; icon: string }[] = [
  { id: 'light', label: 'Light', icon: '☀️' },
  { id: 'dark', label: 'Dark', icon: '🌙' },
  { id: 'system', label: 'System', icon: '💻' },
] as const;

const AVATAR_NAV_LINKS: readonly { to: string; label: string; icon: string }[] = [
  { to: '/settings/mcp', label: 'Personal MCP Keys', icon: '🔑' },
  { to: '/workspaces/settings/mcp', label: 'Workspace MCP Keys', icon: '🏢' },
  { to: '/admin/auth', label: 'Admin Auth Studio', icon: '🛡️' },
  { to: '/admin/mcp', label: 'Admin MCP Keys', icon: '🤖' },
  { to: '/admin/standalone', label: 'Standalone Status & Backup', icon: '💾' },
] as const;

export function Topbar({
  isSidebarOpen = true,
  onToggleSidebar,
  onOpenPalette,
  projectKey = 'KAN',
  projectName = 'kanban',
  currentSection = 'Work Items',
  issueCount,
  showLayoutSwitcher: showLayoutOverride,
  accessManifest,
  systemStatus,
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
          projectId={projectKey}
          projectName={projectName}
          accessManifest={accessManifest}
          systemStatus={systemStatus}
        />

        {isIssuesRoute && <LayoutSwitcher />}

        <div ref={avatarRef} className="kb-avatar-wrapper">
          <button
            type="button"
            className="kb-avatar-button"
            aria-label="User profile and settings"
            aria-haspopup="menu"
            aria-expanded={avatarMenuOpen}
            onClick={() => {
              setAvatarMenuOpen(!avatarMenuOpen);
            }}
          >
            A
          </button>

          {avatarMenuOpen && (
            <div
              className="kb-avatar-menu"
              role="menu"
              aria-label="User settings"
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
                {AVATAR_NAV_LINKS.map((link) => (
                  <Link
                    key={link.to}
                    to={link.to}
                    role="menuitem"
                    className="kb-theme-radio kb-avatar-menu-link"
                    onClick={() => {
                      setAvatarMenuOpen(false);
                    }}
                  >
                    <span>
                      <span aria-hidden="true" className="kb-avatar-menu-icon">
                        {link.icon}
                      </span>
                      {link.label}
                    </span>
                  </Link>
                ))}
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
