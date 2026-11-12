import React, { useState, type JSX } from 'react';
import { ViewHost } from '../features/views/viewRegistry';
import type { IssueItem } from '../features/views/viewsApi';

export interface IssuesWorkspaceRouteProps {
  projectKey: string;
  modulesEnabled?: boolean;
  initialIssues?: IssueItem[];
}

/**
 * Route component mounted on /projects/:projectKey/issues (KB-P3-38).
 * Defaults to layout=list and renders ListView or TableView via ViewHost.
 */
export function IssuesWorkspaceRoute({
  projectKey,
  modulesEnabled = true,
  initialIssues = [],
}: IssuesWorkspaceRouteProps): JSX.Element {
  const [layout] = useState<string>(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get('layout') ?? 'list';
    } catch {
      return 'list';
    }
  });
  const [issues] = useState<IssueItem[]>(initialIssues);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const handleToggleSelect = (key: string, selected: boolean) => {
    setSelectedIds((prev) =>
      selected ? [...prev, key] : prev.filter((id) => id !== key)
    );
  };

  const handleSelectAll = (selected: boolean) => {
    setSelectedIds(selected ? issues.map((i) => i.key) : []);
  };

  return (
    <div className="issues-workspace-route">
      <ViewHost
        layout={layout}
        issues={issues}
        projectKey={projectKey}
        modulesEnabled={modulesEnabled}
        selectedIds={selectedIds}
        onToggleSelect={handleToggleSelect}
        onSelectAll={handleSelectAll}
      />
    </div>
  );
}
