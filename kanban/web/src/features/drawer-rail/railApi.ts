import { apiFetch, type ApiFetchOptions } from '../../api/client';
import type { IssueDetail } from '../drawer/slots';

export interface ProjectPriority {
  id?: string;
  slug: string;
  label?: string;
  name?: string;
  emoji?: string;
  icon?: string;
  sort_order?: number;
  sla_target?: string | null;
}

export interface AssigneeSuggestionItem {
  id: string;
  handle: string;
  display_name: string;
  type: 'USER' | 'AGENT' | (string & {});
}

export interface PrincipalAssignee {
  id: string;
  kind: 'principal';
  principal: {
    id: string;
    handle: string;
    display_name: string;
    type: string;
  };
}

export interface FreeTextAssignee {
  id: string;
  kind: 'free_text';
  free_text: string;
  notify?: boolean;
  hint?: string;
}

export type AssigneeItem = PrincipalAssignee | FreeTextAssignee;

export interface ProjectModule {
  id: string;
  name: string;
  emoji?: string;
  description?: string | null;
  status?: string;
}

export interface ProjectCycle {
  id: string;
  name: string;
  status?: 'upcoming' | 'active' | 'completed' | (string & {});
  completed_count?: number;
  issue_count?: number;
}

export interface ProjectLabel {
  id: string;
  name: string;
  color?: string;
  exclusive_group?: string | null;
}

export interface ProjectWorkflowState {
  id: string;
  name: string;
  group: 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled';
  wip_soft?: number | null;
  wip_hard?: number | null;
}

export interface ProjectMetadata {
  key: string;
  name: string;
  modules_enabled?: boolean;
  states?: ProjectWorkflowState[];
  priorities?: ProjectPriority[];
  labels?: ProjectLabel[];
}

export async function fetchProjectMetadata(projectKey: string): Promise<ProjectMetadata> {
  if (!projectKey || projectKey === 'undefined') {
    return { key: projectKey || '', name: projectKey || '' };
  }
  const res = await apiFetch('GET', '/api/v1/projects/{project_ref}' as never, {
    params: { project_ref: projectKey },
  });
  return res as ProjectMetadata;
}

export async function patchIssue(
  key: string,
  patch: Record<string, unknown>,
  ifMatch?: string,
): Promise<IssueDetail> {
  const opts: ApiFetchOptions = {
    params: { issue_ref: key },
    body: patch,
  };
  if (ifMatch !== undefined) {
    opts.ifMatch = ifMatch;
  }
  const res = await apiFetch('PATCH', '/api/v1/issues/{issue_ref}' as never, opts);
  return res as IssueDetail;
}

export async function fetchProjectPriorities(projectKey: string): Promise<ProjectPriority[]> {
  if (!projectKey || projectKey === 'undefined') {
    return [];
  }
  const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/priorities' as never, {
    params: { project_ref: projectKey },
  });
  const data = res as { items?: ProjectPriority[] } | ProjectPriority[] | undefined;
  if (Array.isArray(data)) {
    return data;
  }
  return data?.items ?? [];
}

export async function fetchAssigneeSuggestions(
  projectKey: string,
  query: string,
  limit = 10,
): Promise<AssigneeSuggestionItem[]> {
  if (!projectKey || projectKey === 'undefined') {
    return [];
  }
  const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/assignee-suggestions' as never, {
    params: { project_ref: projectKey },
    query: { q: query, limit },
  });
  return (res as { items?: AssigneeSuggestionItem[] }).items ?? [];
}

export async function addAssignee(
  key: string,
  payload: { principal?: string; free_text?: string },
): Promise<AssigneeItem> {
  const res = await apiFetch('POST', '/api/v1/issues/{issue_ref}/assignees' as never, {
    params: { issue_ref: key },
    body: payload,
  });
  return res as AssigneeItem;
}

export async function removeAssignee(key: string, assigneeId: string): Promise<void> {
  await apiFetch('DELETE', '/api/v1/issues/{issue_ref}/assignees/{assignee_id}' as never, {
    params: { issue_ref: key, assignee_id: assigneeId },
  });
}

export async function overrideCreator(
  key: string,
  payload: { created_by: string; reason: string },
): Promise<IssueDetail> {
  const res = await apiFetch('PATCH', '/api/v1/issues/{issue_ref}/created-by' as never, {
    params: { issue_ref: key },
    body: payload,
  });
  return res as IssueDetail;
}

export async function fetchProjectModules(projectKey: string): Promise<ProjectModule[]> {
  if (!projectKey || projectKey === 'undefined') {
    return [];
  }
  const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/modules' as never, {
    params: { project_ref: projectKey },
  });
  const data = res as { items?: ProjectModule[] } | ProjectModule[] | undefined;
  if (Array.isArray(data)) {
    return data;
  }
  return data?.items ?? [];
}

export async function updateIssueModules(key: string, moduleIds: string[]): Promise<void> {
  await apiFetch('PUT', '/api/v1/issues/{issue_ref}/modules' as never, {
    params: { issue_ref: key },
    body: { module_ids: moduleIds },
  });
}

export async function fetchProjectCycles(projectKey: string): Promise<ProjectCycle[]> {
  if (!projectKey || projectKey === 'undefined') {
    return [];
  }
  const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/cycles' as never, {
    params: { project_ref: projectKey },
  });
  const data = res as { items?: ProjectCycle[] } | ProjectCycle[] | undefined;
  if (Array.isArray(data)) {
    return data;
  }
  return data?.items ?? [];
}

export async function fetchProjectLabels(projectKey: string): Promise<ProjectLabel[]> {
  if (!projectKey || projectKey === 'undefined') {
    return [];
  }
  const res = await apiFetch('GET', '/api/v1/projects/{project_ref}/labels' as never, {
    params: { project_ref: projectKey },
  });
  const data = res as { items?: ProjectLabel[] } | ProjectLabel[] | undefined;
  if (Array.isArray(data)) {
    return data;
  }
  return data?.items ?? [];
}

export async function createProjectLabel(
  projectKey: string,
  payload: { name: string; color?: string; color_hex?: string; exclusive_group?: string | null },
): Promise<ProjectLabel> {
  if (!projectKey || projectKey === 'undefined') {
    throw new Error('Project key is required to create a label');
  }
  const body: Record<string, unknown> = {
    name: payload.name,
  };
  const colorHex = payload.color_hex || payload.color;
  if (colorHex) {
    body.color_hex = colorHex;
  }
  if (payload.exclusive_group !== undefined) {
    body.exclusive_group = payload.exclusive_group;
  }
  const res = await apiFetch('POST', '/api/v1/projects/{project_ref}/labels' as never, {
    params: { project_ref: projectKey },
    body,
  });
  return res as ProjectLabel;
}
