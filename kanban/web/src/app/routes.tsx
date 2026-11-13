import type { JSX } from 'react';
import { IssuesWorkspaceRoute } from '../features/views/viewRegistry.tsx';

/**
 * Client router matching /projects/:projectKey/issues (KB-P3-37, KB-P3-34).
 */
export function AppRoutes(): JSX.Element | null {
  const pathname = window.location.pathname;
  const match = /^\/projects\/([^/]+)\/issues\/?$/.exec(pathname);

  if (match?.[1]) {
    const projectKey = decodeURIComponent(match[1]);
    return <IssuesWorkspaceRoute projectKey={projectKey} />;
  }

  return null;
}
