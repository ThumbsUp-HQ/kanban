// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { Link, useInRouterContext, useLocation } from 'react-router';
import { QueryClientContext } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { apiFetch } from '../../api/client';
import './AdminStudioSubnav.css';

export interface AdminStudioSubnavProps {
  activeTab?: 'auth' | 'ai' | 'runners' | 'mcp' | 'oauth' | 'imports' | 'standalone' | 'diagnostics' | undefined;
  isServerAdmin?: boolean | undefined;
}

interface AdminTabDefinition {
  id: 'auth' | 'ai' | 'runners' | 'mcp' | 'oauth' | 'imports' | 'standalone' | 'diagnostics';
  testId: string;
  label: string;
  path: string;
  icon: string;
  serverOnly?: boolean;
}

const ADMIN_TABS: AdminTabDefinition[] = [
  { id: 'auth', testId: 'tab-admin-auth', label: 'Auth Cards', path: '/admin/auth', icon: '🛡️', serverOnly: true },
  { id: 'ai', testId: 'tab-admin-ai', label: 'AI Providers', path: '/admin/ai', icon: '🧠', serverOnly: true },
  { id: 'runners', testId: 'tab-admin-runners', label: 'Remote Runners', path: '/admin/agent-runners', icon: '🚀', serverOnly: true },
  { id: 'mcp', testId: 'tab-admin-mcp', label: 'Bot API Keys', path: '/admin/mcp', icon: '🔑', serverOnly: true },
  { id: 'oauth', testId: 'tab-admin-oauth', label: 'OAuth 2.1 Clients', path: '/admin/oauth', icon: '🌐', serverOnly: true },
  { id: 'imports', testId: 'tab-admin-imports', label: 'Migration', path: '/admin/imports', icon: '📥', serverOnly: true },
  { id: 'standalone', testId: 'tab-admin-standalone', label: 'System & Backups', path: '/admin/standalone', icon: '💾', serverOnly: true },
  { id: 'diagnostics', testId: 'tab-admin-diagnostics', label: 'Diagnostics', path: '/admin/diagnostics', icon: '🩺', serverOnly: false },
];

function AdminStudioSubnavInner({
  activeTab,
  currentPath,
  inRouter,
  isServerAdmin,
}: AdminStudioSubnavProps & { currentPath: string; inRouter: boolean }): JSX.Element {
  const queryClient = React.useContext(QueryClientContext);
  const cachedMe = queryClient
    ? queryClient.getQueryData<{ is_server_admin?: boolean }>(qk.me())
    : undefined;
  const effectiveIsServerAdmin = isServerAdmin ?? cachedMe?.is_server_admin ?? false;

  const [sessionData, setSessionData] = React.useState<{
    authenticated?: boolean;
    aal2_active?: boolean;
    aal2_expires_at?: string | null;
  } | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    const load = async (): Promise<void> => {
      try {
        const res = (await apiFetch('GET', '/api/v1/auth/session')) as {
          authenticated?: boolean;
          aal2_active?: boolean;
          aal2_expires_at?: string | null;
        };
        if (!cancelled) {
          setSessionData(res);
        }
      } catch {
        if (!cancelled) {
          setSessionData(null);
        }
      }
    };
    void load();
    const interval = setInterval(() => {
      void load();
    }, 10_000);

    const onStepupSuccess = (): void => {
      void load();
    };

    const onExpiresAt = (e: Event): void => {
      const custom = e as CustomEvent<{ expiresAt?: string } | undefined>;
      const expiresAt = custom.detail?.expiresAt;
      if (expiresAt && !cancelled) {
        setSessionData(() => ({
          authenticated: true,
          aal2_active: true,
          aal2_expires_at: expiresAt,
        }));
      }
      void load();
    };

    window.addEventListener('kb:aal2-stepup-success', onStepupSuccess);
    window.addEventListener('kb:aal2-expires-at', onExpiresAt);

    return () => {
      cancelled = true;
      clearInterval(interval);
      window.removeEventListener('kb:aal2-stepup-success', onStepupSuccess);
      window.removeEventListener('kb:aal2-expires-at', onExpiresAt);
    };
  }, []);

  const aal2Active = sessionData?.aal2_active;
  const aal2ExpiresAt = sessionData?.aal2_expires_at;

  const [now, setNow] = React.useState<number>(() => Date.now());

  React.useEffect(() => {
    if (!aal2Active || !aal2ExpiresAt) {
      return;
    }
    const interval = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      clearInterval(interval);
    };
  }, [aal2Active, aal2ExpiresAt]);

  const remainingSecs = React.useMemo<number | null>(() => {
    if (!aal2Active || !aal2ExpiresAt) {
      return null;
    }
    const exp = new Date(aal2ExpiresAt).getTime();
    return Math.max(0, Math.floor((exp - now) / 1000));
  }, [aal2Active, aal2ExpiresAt, now]);

  const handleDrop = async (e: React.MouseEvent): Promise<void> => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await apiFetch('POST', '/api/v1/auth/aal2/drop');
    } catch {
      // Ignore network errors on drop
    }
    void queryClient?.invalidateQueries();
    try {
      const res = (await apiFetch('GET', '/api/v1/auth/session')) as {
        authenticated?: boolean;
        aal2_active?: boolean;
        aal2_expires_at?: string | null;
      };
      setSessionData(res);
    } catch {
      setSessionData(null);
    }
  };

  const formatTime = (secs: number): string => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${String(m)}:${s < 10 ? '0' : ''}${String(s)}`;
  };

  const visibleTabs = effectiveIsServerAdmin
    ? ADMIN_TABS
    : ADMIN_TABS.filter((tab) => !tab.serverOnly);

  return (
    <nav className="kb-mcp-admin-subnav admin-studio-subnav" aria-label="Admin MCP and Governance Navigation">
      <div className="admin-studio-subnav__scroll">
        {visibleTabs.map((tab) => {
          const isActive = activeTab
            ? activeTab === tab.id
            : currentPath === tab.path || currentPath.startsWith(`${tab.path}/`);

          const className = `kb-mcp-admin-subnav-link admin-studio-subnav__item ${
            isActive ? 'kb-mcp-admin-subnav-active admin-studio-subnav__item--active' : ''
          }`;

          return inRouter ? (
            <Link
              key={tab.id}
              to={tab.path}
              className={className}
              data-testid={tab.testId}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className="admin-studio-subnav__icon" aria-hidden="true">
                {tab.icon}
              </span>
              <span>{tab.label}</span>
            </Link>
          ) : (
            <a
              key={tab.id}
              href={tab.path}
              className={className}
              data-testid={tab.testId}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className="admin-studio-subnav__icon" aria-hidden="true">
                {tab.icon}
              </span>
              <span>{tab.label}</span>
            </a>
          );
        })}
      </div>
      <div className="admin-studio-subnav__actions">
        <div
          className={`admin-sudo-pill ${sessionData?.aal2_active ? 'admin-sudo-pill--active' : 'admin-sudo-pill--locked'}`}
          data-testid="admin-sudo-pill"
        >
          {sessionData?.aal2_active ? (
            <>
              <span className="admin-sudo-pill__status" title="AAL2 Admin WebSudo Active">
                🛡️ Sudo {remainingSecs !== null ? formatTime(remainingSecs) : 'Active'}
              </span>
              <button
                type="button"
                className="admin-sudo-pill__drop-btn"
                onClick={(e) => {
                  void handleDrop(e);
                }}
                title="Lock WebSudo Session"
                aria-label="Drop WebSudo Elevation"
                data-testid="admin-sudo-drop-btn"
              >
                🔒 Lock
              </button>
            </>
          ) : (
            <span className="admin-sudo-pill__status" title="AAL2 WebSudo Locked">
              🔒 Sudo Locked
            </span>
          )}
        </div>
      </div>
    </nav>
  );
}

function AdminStudioSubnavWithRouter({ activeTab, isServerAdmin }: AdminStudioSubnavProps): JSX.Element {
  const location = useLocation();
  return (
    <AdminStudioSubnavInner
      activeTab={activeTab}
      isServerAdmin={isServerAdmin}
      currentPath={location.pathname}
      inRouter={true}
    />
  );
}

export function AdminStudioSubnav({ activeTab, isServerAdmin }: AdminStudioSubnavProps): JSX.Element {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return <AdminStudioSubnavWithRouter activeTab={activeTab} isServerAdmin={isServerAdmin} />;
  }
  const currentPath = window.location.pathname;
  return (
    <AdminStudioSubnavInner
      activeTab={activeTab}
      isServerAdmin={isServerAdmin}
      currentPath={currentPath}
      inRouter={false}
    />
  );
}
