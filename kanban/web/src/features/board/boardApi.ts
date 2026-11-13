/**
 * Board API client and cache manipulation functions (KB-P3-37, KB-P3-12, S6.4).
 */

import { apiFetch } from '../../api/client.ts';

export interface BoardPriority {
  id: string;
  label: string;
  slug: string;
  color_hex?: string;
}

export interface BoardAssignee {
  id: string;
  name?: string;
  display_name?: string;
  handle?: string;
  is_agent?: boolean;
  free_text?: string;
}

export interface BoardCycle {
  id: string;
  name: string;
}

export interface BoardIssue {
  id: string;
  key: string;
  summary: string;
  state_id: string;
  priority?: BoardPriority | null;
  board_rank: string;
  assignees?: BoardAssignee[];
  cycle?: BoardCycle | null;
  due_date?: string | null;
  gate_status?: 'pending' | 'rejected' | 'approved' | null;
  has_explicit_acl?: boolean;
}

export type StateGroup = 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled';

export interface BoardWorkflowState {
  id: string;
  name: string;
  slug?: string;
  group: StateGroup;
  sort_order: number;
  wip_soft_limit?: number | null;
  wip_hard_limit?: number | null;
}

export interface IssueMoveParams {
  projectKey: string;
  issueKey: string;
  targetStateId?: string;
  afterIssueKey?: string | null;
  beforeIssueKey?: string | null;
  boardRank?: string;
  wipOverrideReason?: string;
  overrideWip?: boolean;
}

export interface IssueMoveResponse {
  issue_key: string;
  state_id: string;
  board_rank: string;
  rebalance_scheduled: boolean;
  wip_warning?: {
    soft_limit: number;
    resulting_count: number;
  } | null;
}

/**
 * Dispatch POST /api/v1/issues/{issue_ref}/move (KB-P3-12).
 */
export async function moveIssueApi(params: IssueMoveParams): Promise<IssueMoveResponse> {
  const body: Record<string, unknown> = {
    override_wip: params.overrideWip ?? false,
  };
  if (params.targetStateId) {
    body.target_state_id = params.targetStateId;
  }
  if (params.afterIssueKey) {
    body.after_issue = params.afterIssueKey;
  }
  if (params.beforeIssueKey) {
    body.before_issue = params.beforeIssueKey;
  }
  if (params.wipOverrideReason) {
    body.wip_override_reason = params.wipOverrideReason;
  }

  const rawFetch = apiFetch as unknown as (
    method: string,
    path: string,
    options: unknown,
  ) => Promise<IssueMoveResponse>;

  return rawFetch('POST', '/api/v1/issues/{issue_ref}/move', {
    params: { issue_ref: params.issueKey },
    body,
  });
}

/**
 * Synchronous 1-row cache updater.
 * Replaces strictly the moved issue object reference in the array.
 * Completes well under the < 12ms budget even on 500+ items.
 */
export function applyOptimisticMove(
  cache: BoardIssue[] | undefined,
  params: IssueMoveParams,
): BoardIssue[] {
  if (!cache || cache.length === 0) {
    return [];
  }

  const target = cache.find((item) => item.key === params.issueKey);
  if (!target) {
    return cache;
  }

  const updated: BoardIssue = {
    id: target.id,
    key: target.key,
    summary: target.summary,
    state_id: params.targetStateId ?? target.state_id,
    board_rank: params.boardRank ?? target.board_rank,
    ...(target.priority !== undefined ? { priority: target.priority } : {}),
    ...(target.assignees !== undefined ? { assignees: target.assignees } : {}),
    ...(target.cycle !== undefined ? { cycle: target.cycle } : {}),
    ...(target.due_date !== undefined ? { due_date: target.due_date } : {}),
    ...(target.gate_status !== undefined ? { gate_status: target.gate_status } : {}),
    ...(target.has_explicit_acl !== undefined ? { has_explicit_acl: target.has_explicit_acl } : {}),
  };

  return cache.map((item) => (item.key === params.issueKey ? updated : item));
}
