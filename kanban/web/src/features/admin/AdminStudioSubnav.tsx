// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { Link, useInRouterContext, useLocation } from 'react-router';
import './AdminStudioSubnav.css';

export interface AdminStudioSubnavProps {
  activeTab?: 'auth' | 'ai' | 'runners' | 'mcp' | 'oauth' | 'imports' | 'standalone' | 'diagnostics' | undefined;
}

interface AdminTabDefinition {
  id: 'auth' | 'ai' | 'runners' | 'mcp' | 'oauth' | 'imports' | 'standalone' | 'diagnostics';
  testId: string;
  label: string;
  path: string;
  icon: string;
}

const ADMIN_TABS: AdminTabDefinition[] = [
  { id: 'auth', testId: 'tab-admin-auth', label: 'Auth Cards', path: '/admin/auth', icon: '🛡️' },
  { id: 'ai', testId: 'tab-admin-ai', label: 'AI Providers', path: '/admin/ai', icon: '🧠' },
  { id: 'runners', testId: 'tab-admin-runners', label: 'Remote Runners', path: '/admin/agent-runners', icon: '🚀' },
  { id: 'mcp', testId: 'tab-admin-mcp', label: 'Bot API Keys', path: '/admin/mcp', icon: '🔑' },
  { id: 'oauth', testId: 'tab-admin-oauth', label: 'OAuth 2.1 Clients', path: '/admin/oauth', icon: '🌐' },
  { id: 'imports', testId: 'tab-admin-imports', label: 'Plane Migration', path: '/admin/imports', icon: '📥' },
  { id: 'standalone', testId: 'tab-admin-standalone', label: 'System & Backups', path: '/admin/standalone', icon: '💾' },
  { id: 'diagnostics', testId: 'tab-admin-diagnostics', label: 'Diagnostics', path: '/admin/diagnostics', icon: '🩺' },
];

function AdminStudioSubnavInner({
  activeTab,
  currentPath,
  inRouter,
}: AdminStudioSubnavProps & { currentPath: string; inRouter: boolean }): JSX.Element {
  return (
    <nav className="kb-mcp-admin-subnav admin-studio-subnav" aria-label="Admin MCP and Governance Navigation">
      <div className="admin-studio-subnav__scroll">
        {ADMIN_TABS.map((tab) => {
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

function AdminStudioSubnavWithRouter({ activeTab }: AdminStudioSubnavProps): JSX.Element {
  const location = useLocation();
  return <AdminStudioSubnavInner activeTab={activeTab} currentPath={location.pathname} inRouter={true} />;
}

export function AdminStudioSubnav({ activeTab }: AdminStudioSubnavProps): JSX.Element {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return <AdminStudioSubnavWithRouter activeTab={activeTab} />;
  }
  const currentPath = window.location.pathname;
  return <AdminStudioSubnavInner activeTab={activeTab} currentPath={currentPath} inRouter={false} />;
}
