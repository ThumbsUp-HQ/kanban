/**
 * Canonical TanStack Query key factory for the Kanban frontend (KB-P3-33).
 */

export const qk = {
  me: () => ['me'] as const,
  systemStatus: () => ['system', 'status'] as const,
  projects: () => ['projects'] as const,
  savedViews: (projectKey: string) => ['views', projectKey] as const,
  notifications: (unreadOnly?: boolean) => ['notifications', Boolean(unreadOnly)] as const,
  project: (key: string) => ['project', key] as const,
  issues: (projectKey: string, filters: Readonly<Record<string, unknown>>) =>
    ['issues', projectKey, filters] as const,
  issue: (issueKey: string) => ['issue', issueKey] as const,
  activity: (issueKey: string, tab: 'all' | 'comments' | 'history' | 'gates') =>
    ['activity', issueKey, tab] as const,
  access: (objectId: string) => ['access', objectId] as const,
  authCards: () => ['auth', 'cards'] as const,
  adminAuthCards: () => ['admin', 'auth', 'cards'] as const,
  docsTree: (projectKey: string) => ['docs', 'tree', projectKey] as const,
  page: (pageId: string) => ['docs', 'page', pageId] as const,
  stickies: (projectKey: string) => ['stickies', projectKey] as const,
  subscription: (key: string) => ['subscription', key] as const,
  objectLinks: (key: string) => ['objectLinks', key] as const,
  canonicalUrl: (key: string) => ['canonicalUrl', key] as const,
  deletePreview: (key: string) => ['deletePreview', key] as const,
  systemAbout: () => ['system', 'about'] as const,
};
