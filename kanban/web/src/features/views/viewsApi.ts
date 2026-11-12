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

  return (await response.json()) as { items: IssueItem[]; next_cursor: string | null; total?: number };
}
