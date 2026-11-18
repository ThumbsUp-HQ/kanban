// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { createContext, useContext } from 'react';

export interface ProjectRouteContextValue {
  readonly projectKey: string;
  readonly projectName: string;
  readonly modulesEnabled: boolean;
  readonly capabilities: string[];
  readonly isProjectAdmin: boolean;
}

export const ProjectRouteContext = createContext<ProjectRouteContextValue>({
  projectKey: '',
  projectName: '',
  modulesEnabled: true,
  capabilities: [],
  isProjectAdmin: false,
});

export function useProjectRouteContext(): ProjectRouteContextValue {
  return useContext(ProjectRouteContext);
}
