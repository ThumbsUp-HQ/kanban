// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { Link, useInRouterContext, useLocation } from 'react-router';
import { QueryClientContext } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
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
  const effectiveIsServerAdmin = isServerAdmin ?? cachedMe?.is_server_admin ?? true;

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
