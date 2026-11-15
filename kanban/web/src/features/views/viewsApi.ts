/**
 * Typed views API interfaces and fetch helpers (KB-P3-38, KB-P3-11, S6.4).
 */

export interface StateSummary {
  id: string;
  name: string;
  group: string;
  sort_order?: number;
}

export interface PrioritySummary {
  slug: string;
  label: string;
  emoji?: string | null;
  sort_order?: number;
}

export interface LabelSummary {
  id: string;
  name: string;
  color_hex: string;
}

export interface PrincipalSummary {
  id: string;
  handle: string;
  display_name: string;
  type: string;
}

export interface PrincipalAssignee {
  id: string;
  kind: 'principal';
  principal: PrincipalSummary;
}

export interface FreeTextAssignee {
  id: string;
  kind: 'free_text';
  free_text: string;
  notify: boolean;
  hint: string;
}

export type AssigneeItem = PrincipalAssignee | FreeTextAssignee;

export interface NormalParentSummary {
  key: string;
  summary: string;
}

export interface RestrictedParentSummary {
  restricted: true;
  label: string;
}

export interface IssueItem {
  id: string;
  key: string;
  summary: string;
  description_markdown?: string;
  description_sha256?: string;
  state: StateSummary;
  priority: PrioritySummary;
  start_date?: string | null;
  due_date?: string | null;
  cycle_id?: string | null;
  parent?: NormalParentSummary | RestrictedParentSummary | null;
  labels?: LabelSummary[];
  module_ids?: string[] | null;
  assignees?: AssigneeItem[];
  board_rank?: string;
  created_by_id?: string;
  created_by_handle?: string;
  has_explicit_acl?: boolean;
  gate_status?: 'pending' | 'vetoed' | 'approved' | null;
  capabilities?: string[];
  archived_at?: string | null;
  outbound_blocks?: {
    target_key?: string;
    link_state?: string;
    restricted?: boolean;
  }[];
  links?: {
    id?: string | undefined;
    source_key?: string | undefined;
    target_key?: string | null | undefined;
    link_type?: string | undefined;
    link_state?: string | undefined;
    restricted?: boolean | undefined;
    label?: string | undefined;
  }[];
}

export interface ProjectMetadata {
  id?: string;
  key: string;
  name: string;
  modules_enabled: boolean;
}

export type ViewLayout = 'board' | 'list' | 'table' | 'calendar' | 'timeline';
export type GroupAxis = 'none' | 'state' | 'priority' | 'assignee' | 'cycle' | 'module' | 'label';
export type SortDirection = 'asc' | 'desc' | 'none';

export interface SavedView {
  id: string;
  project_id?: string | null;
  name: string;
  description_markdown?: string;
  layout: ViewLayout;
  group_by: GroupAxis;
  sub_group_by: GroupAxis;
  display_json?: {
    table_columns?: string[];
  };
}

export interface IssueQueryParams {
  tab?: string;
  layout?: ViewLayout;
  group_by?: GroupAxis;
  sort_by?: string;
  sort_dir?: SortDirection;
  cursor?: string | null;
  limit?: number;
}

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuidString(value: string | null | undefined): boolean {
  return Boolean(value && UUID_REGEX.test(value));
}

/**
 * Normalize a workflow state name or slug for comparison ("To Do" === "Todo" -> "todo").
 */
export function normalizeStateKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, '');
}

export function extractCsrfFromCookieString(cookieStr: string): string | null {
  if (!cookieStr) return null;
  const parts = cookieStr.split(';');
  for (const raw of parts) {
    const trimmed = raw.trim();
    if (trimmed.startsWith('__Host-kb_csrf=')) {
      return decodeURIComponent(trimmed.slice('__Host-kb_csrf='.length));
    }
    if (trimmed.startsWith('kb_csrf=')) {
      return decodeURIComponent(trimmed.slice('kb_csrf='.length));
    }
  }
  return null;
}

/**
 * Read CSRF token from document.cookie or bootstrap via GET /api/v1/auth/session.
 */
export async function ensureCsrfToken(): Promise<string | null> {
  const initialCookie = typeof document !== 'undefined' ? document.cookie : '';
  const fromCookie = extractCsrfFromCookieString(initialCookie);
  if (fromCookie) {
    return fromCookie;
  }
  try {
    const resp = await fetch('/api/v1/auth/session', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    if (resp.ok) {
      const body = (await resp.json()) as { csrf_token?: string };
      if (body.csrf_token) {
        return body.csrf_token;
      }
    }
  } catch {
    // Ignore bootstrap errors in offline/unit test environments
  }
  const updatedCookie = typeof document !== 'undefined' ? document.cookie : '';
  return extractCsrfFromCookieString(updatedCookie);
}

/**
 * Normalize backend IssueResponse payload into the frontend IssueItem contract.
 */
export function normalizeIssueItem(raw: Partial<IssueItem> & Record<string, unknown>): IssueItem {
  const rawState = raw.state ?? { id: 'state-todo', name: 'Todo', group: 'unstarted' };
  const normalizedStateName =
    normalizeStateKey(rawState.name) === 'todo' ? 'Todo' : rawState.name;

  const rawPriority = raw.priority ?? {
    slug: 'medium',
    label: 'Medium',
    emoji: '🔹',
  };

  const provenance = raw.provenance as
    | { created_by?: { id?: string; handle?: string } }
    | undefined;
  const accessManifest = raw.access_manifest as
    | { explicit_grant_count?: number }
    | undefined;

  const createdByHandle =
    raw.created_by_handle ?? provenance?.created_by?.handle;
  const createdById =
    raw.created_by_id ?? provenance?.created_by?.id;
  const hasExplicitAcl =
    raw.has_explicit_acl ??
    (typeof accessManifest?.explicit_grant_count === 'number'
      ? accessManifest.explicit_grant_count > 0
      : undefined);

  const item: IssueItem = {
    ...raw,
    id: raw.id ?? '',
    key: raw.key ?? '',
    summary: raw.summary ?? '',
    state: {
      ...rawState,
      name: normalizedStateName,
    },
    priority: rawPriority,
  };

  if (createdByHandle !== undefined) {
    item.created_by_handle = createdByHandle;
  }
  if (createdById !== undefined) {
    item.created_by_id = createdById;
  }
  if (hasExplicitAcl !== undefined) {
    item.has_explicit_acl = hasExplicitAcl;
  }

  return item;
}

/**
 * Fetch issues list for a project using standard REST query parameters.
 */
export async function fetchProjectIssues(
  projectKey: string,
  params: IssueQueryParams = {}
): Promise<{ items: IssueItem[]; next_cursor: string | null; total?: number }> {
  const searchParams = new URLSearchParams();
  if (params.cursor) searchParams.set('cursor', params.cursor);
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.sort_by) searchParams.set('sort_by', params.sort_by);
  if (params.sort_dir && params.sort_dir !== 'none') searchParams.set('sort_dir', params.sort_dir);

  const queryStr = searchParams.toString();
  const url = `/api/v1/projects/${encodeURIComponent(projectKey)}/issues${queryStr ? `?${queryStr}` : ''}`;

  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch project issues: ${String(response.status)} ${response.statusText}`);
  }

  const data = (await response.json()) as {
    items: (Partial<IssueItem> & Record<string, unknown>)[];
    next_cursor: string | null;
    total?: number;
  };
  return {
    ...data,
    items: data.items.map((item) => normalizeIssueItem(item)),
  };
}

/**
 * Fetch workflow states for a project from GET /api/v1/projects/:projectKey/states.
 */
export async function fetchProjectStates(projectKey: string): Promise<StateSummary[]> {
  const url = `/api/v1/projects/${encodeURIComponent(projectKey)}/states`;
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch project states: ${String(response.status)} ${response.statusText}`);
  }
  const data = (await response.json()) as { items?: StateSummary[] } | StateSummary[];
  if (Array.isArray(data)) {
    return data;
  }
  return data.items ?? [];
}

/**
 * Resolve a StateSummary (which may have a synthetic ID like 'state-todo') against real project states.
 */
export function resolveStateUuid(
  desiredState: StateSummary | undefined,
  projectStates: StateSummary[]
): string | undefined {
  if (!desiredState) return undefined;
  if (isUuidString(desiredState.id)) {
    return desiredState.id;
  }
  const desiredNorm = normalizeStateKey(desiredState.name);
  const byName = projectStates.find(
    (s) => normalizeStateKey(s.name) === desiredNorm && isUuidString(s.id)
  );
  if (byName) return byName.id;

  const byGroup = projectStates.find(
    (s) => s.group === desiredState.group && isUuidString(s.id)
  );
  return byGroup?.id;
}

/**
 * Create a new issue via POST /api/v1/projects/:projectKey/issues with CSRF protection.
 */
export async function createProjectIssue(
  projectKey: string,
  payload: Partial<IssueItem>,
  projectStates: StateSummary[] = []
): Promise<IssueItem> {
  const csrfToken = await ensureCsrfToken();
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  };
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  const body: Record<string, unknown> = {
    summary: payload.summary ?? 'Untitled work item',
    description_markdown: payload.description_markdown ?? '',
    priority: payload.priority?.slug ?? 'medium',
  };

  const resolvedStateId = resolveStateUuid(payload.state, projectStates);
  if (resolvedStateId) {
    body.state_id = resolvedStateId;
  }

  if (payload.module_ids && payload.module_ids.length > 0) {
    const validModuleUuids = payload.module_ids.filter((id) => isUuidString(id));
    if (validModuleUuids.length > 0) {
      body.module_ids = validModuleUuids;
    }
  }

  const url = `/api/v1/projects/${encodeURIComponent(projectKey)}/issues`;
  const response = await fetch(url, {
    method: 'POST',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Failed to create issue: ${String(response.status)} ${response.statusText}`);
  }

  const raw = (await response.json()) as Partial<IssueItem> & Record<string, unknown>;
  return normalizeIssueItem(raw);
}

/**
 * Update an issue via PATCH /api/v1/issues/:issueKey with CSRF protection.
 */
export async function patchProjectIssue(
  issueKey: string,
  patch: Record<string, unknown>,
  ifMatch?: string
): Promise<IssueItem> {
  const csrfToken = await ensureCsrfToken();
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  };
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  if (ifMatch) {
    headers['If-Match'] = ifMatch;
  }

  const url = `/api/v1/issues/${encodeURIComponent(issueKey)}`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify(patch),
  });

  if (!response.ok) {
    throw new Error(`Failed to update issue: ${String(response.status)} ${response.statusText}`);
  }

  const raw = (await response.json()) as Partial<IssueItem> & Record<string, unknown>;
  return normalizeIssueItem(raw);
}

/**
 * Delete an issue via DELETE /api/v1/issues/:issueKey with CSRF protection.
 */
export async function deleteProjectIssue(issueKey: string): Promise<void> {
  const csrfToken = await ensureCsrfToken();
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  const url = `/api/v1/issues/${encodeURIComponent(issueKey)}`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers,
    credentials: 'same-origin',
  });

  if (!response.ok) {
    throw new Error(`Failed to delete issue: ${String(response.status)} ${response.statusText}`);
  }
}
